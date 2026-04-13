# 多模态 RAG 后端服务 API 规范 v1.0

> 基于 MinerU 文档解析 + rag_pipeline 向量索引 + langextract KG 抽取 + agentic_rag 问答的工程化后端服务  
> 编写日期：2026-04-13  
> 技术栈：FastAPI + SQLite + asyncio  
> 上游依赖规范：`mineru-api-spec-v1.0.md` / `mineru-rag_pipeline-spec-v1.0.md` / `mineru-langextract-pipeline-v1.0.md` / `agentic-rag-pipeline-spec-v1.0.md`

---

## 目录

1. [系统架构概览](#1-系统架构概览)
2. [数据流与状态机](#2-数据流与状态机)
3. [目录结构](#3-目录结构)
4. [数据库模型](#4-数据库模型)
5. [API 接口规范](#5-api-接口规范)
   - 5.1 文档管理
   - 5.2 Q&A 问答
   - 5.3 健康检查
6. [错误码规范](#6-错误码规范)
7. [服务层设计](#7-服务层设计)
8. [配置规范](#8-配置规范)
9. [前端对接指南](#9-前端对接指南)
10. [非功能性需求](#10-非功能性需求)

---

## 1. 系统架构概览

### 1.1 整体架构图

```
┌────────────────────────────────────────────────────────────────────┐
│                        前端 / API 调用方                            │
└───────────────────────────┬────────────────────────────────────────┘
                            │ HTTP REST
                            ▼
┌────────────────────────────────────────────────────────────────────┐
│                    Backend Service（FastAPI）                        │
│                                                                    │
│  POST /documents/upload ──→ [mineru_service] ──→ MinerU Cloud API  │
│  GET  /documents/{id}/status ──→ SQLite 状态查询                    │
│  POST /qa/query ──→ [qa_service] ──→ agentic_rag LangGraph          │
│                                                                    │
│  后台任务链：上传完成 → 解析 → 解析完成 → 并行建索引 → READY        │
└─────────┬────────────────────┬──────────────────────┬──────────────┘
          │                    │                      │
          ▼                    ▼                      ▼
   ┌─────────────┐   ┌──────────────────┐   ┌──────────────────────┐
   │ MinerU API  │   │  rag_pipeline    │   │ langextract_pipeline │
   │（云端解析）  │   │  （向量+BM25）   │   │  （KG 实体抽取）      │
   │             │   │  chroma_db/      │   │  output/*.jsonl      │
   └─────────────┘   └──────────────────┘   └──────────────────────┘
                               │                      │
                               └──────────┬───────────┘
                                          ▼
                              ┌───────────────────────┐
                              │     agentic_rag        │
                              │   LangGraph 5 节点     │
                              │  KGRetriever +         │
                              │  HybridRetriever       │
                              └───────────────────────┘
```

### 1.2 技术选型

| 层次 | 选型 | 理由 |
|------|------|------|
| Web 框架 | **FastAPI** | 原生 async、自动 OpenAPI 文档、Pydantic 校验 |
| 状态存储 | **SQLite**（aiosqlite） | 记录文档/任务状态，MVP 无需 PostgreSQL |
| 任务调度 | **asyncio.BackgroundTask** | 解析/索引均为异步长任务，MVP 无需 Celery |
| 文件存储 | **本地磁盘**（uploads/ + mineru_parser/output/） | 与现有 pipeline 目录兼容 |
| 问答引擎 | **agentic_rag**（复用已验证 LangGraph） | 单例懒加载，进程内调用 |

### 1.3 支持的文件格式

| 格式 | 扩展名 | 路由到 | 输出 |
|------|--------|--------|------|
| PDF | `.pdf` | Precision API | full.md + content_list.json + images/ |
| Word | `.doc` `.docx` | Precision API | full.md + content_list.json + images/ |
| PowerPoint | `.ppt` `.pptx` | Precision API | full.md + content_list.json + images/ |
| 图片 | `.jpg` `.jpeg` `.png` `.gif` `.webp` | Precision API | full.md + content_list.json |
| HTML | `.html` `.htm` | Precision API | full.md + content_list.json |
| Excel | `.xls` `.xlsx` | **Agent API** | full.md（仅 Markdown，无结构化 JSON） |

**文件大小限制**：
- Precision API：≤ 200MB，≤ 600 页
- Agent API（Excel）：≤ 10MB，≤ 20 页

---

## 2. 数据流与状态机

### 2.1 文档处理完整数据流

```
① POST /documents/upload
   前端上传文件 → backend 保存到 uploads/{doc_id}.{ext}
   → SQLite 写入 status=UPLOADED
   → BackgroundTask: mineru_service.submit_parse(doc_id)

② mineru_service.submit_parse
   Excel → POST /api/v1/agent/parse/file + PUT presigned_url
          → task_id → 更新 status=PARSING, mineru_api_type=agent
   其他  → POST /api/v4/file-urls/batch + PUT presigned_url
          → batch_id → 更新 status=PARSING, mineru_api_type=precision

③ mineru_service.poll_until_done（后台持续轮询）
   每 10s 轮询 MinerU 状态接口（最多 600s）
   → state=done → 下载 ZIP → 解压到 mineru_parser/output/{doc_id}/
   → 更新 status=PARSED, mineru_output_dir
   → BackgroundTask: index_service.build_both(doc_id)

④ index_service.build_both（两路并行）
   Task A: subprocess → python rag_pipeline/pipeline.py build {doc_id}
           完成 → 更新 vector_status=done, chunk_count
   Task B: subprocess → python langextract_pipeline/run_pipeline.py "{doc_id}"
           完成 → 统计 match_exact 实体数 → 更新 kg_status=done, entity_count
   两路均完成 → 更新 status=READY

⑤ POST /qa/query
   qa_service.run_query(question) → agentic_rag.app.invoke(state)
   → 格式化输出 → 返回结构化 JSON
```

### 2.2 文档状态机

```
              ┌──────────┐
    上传文件   │ UPLOADED │
  ──────────→ └────┬─────┘
                   │ 提交 MinerU 任务
                   ▼
             ┌──────────┐
             │ PARSING  │ ←── MinerU 解析中（最多 600s）
             └────┬─────┘
          ┌───────┴──────────┐
      失败 │                  │ 成功
          ▼                  ▼
   ┌──────────────┐    ┌──────────┐
   │ PARSE_FAILED │    │  PARSED  │
   └──────────────┘    └────┬─────┘
                            │ 触发并行索引构建
                            ▼
                      ┌──────────┐
                      │ INDEXING │ ←── 向量+KG 并行构建中
                      └────┬─────┘
                   ┌───────┴──────────┐
               失败 │                  │ 成功
                   ▼                  ▼
          ┌──────────────┐      ┌──────────┐
          │ INDEX_FAILED │      │  READY   │ ←── 可问答
          └──────────────┘      └──────────┘
```

### 2.3 子状态字段

`vector_status` 和 `kg_status` 分别独立跟踪：

| 值 | 含义 |
|----|------|
| `pending` | 等待触发 |
| `building` | 构建中 |
| `done` | 完成 |
| `failed` | 失败 |

---

## 3. 目录结构

```
GraphRagAgent/
└── backend/
    ├── main.py                      # FastAPI 应用入口，注册路由
    ├── config.py                    # 配置加载（读 .env）
    ├── models.py                    # Pydantic 请求/响应模型
    ├── database.py                  # SQLite 初始化与 CRUD（aiosqlite）
    ├── routers/
    │   ├── __init__.py
    │   ├── documents.py             # 文档上传、状态查询、列表、删除
    │   ├── qa.py                    # Q&A 问答端点
    │   └── health.py                # 健康检查
    ├── services/
    │   ├── __init__.py
    │   ├── mineru_service.py        # MinerU Precision + Agent API 封装
    │   ├── index_service.py         # 并行触发向量+KG 索引构建
    │   └── qa_service.py            # 封装 agentic_rag，格式化输出
    ├── data/
    │   └── jobs.db                  # SQLite 数据库文件（自动创建）
    ├── uploads/                     # 原始上传文件临时存储
    ├── .env                         # 实际配置（不提交 git）
    ├── .env.example                 # 配置模板
    ├── requirements.txt             # 依赖清单
    └── CLAUDE.md                    # 运维操作手册
```

---

## 4. 数据库模型

### 4.1 documents 表 DDL

```sql
CREATE TABLE IF NOT EXISTS documents (
    doc_id          TEXT PRIMARY KEY,
    filename        TEXT NOT NULL,
    file_type       TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'UPLOADED',
    mineru_api_type TEXT,                   -- precision | agent
    mineru_batch_id TEXT,                   -- Precision API batch_id
    mineru_task_id  TEXT,                   -- Agent API task_id
    mineru_output_dir TEXT,                 -- 解析结果目录绝对路径
    vector_status   TEXT DEFAULT 'pending', -- pending|building|done|failed
    kg_status       TEXT DEFAULT 'pending', -- pending|building|done|failed
    chunk_count     INTEGER,                -- 向量 chunk 数
    entity_count    INTEGER,                -- KG match_exact 实体数
    error_msg       TEXT,
    created_at      TEXT NOT NULL,          -- ISO8601
    updated_at      TEXT NOT NULL           -- ISO8601
);
```

### 4.2 Pydantic 响应模型

```python
class DocumentStatus(BaseModel):
    doc_id: str
    filename: str
    file_type: str
    status: str                     # UPLOADED|PARSING|PARSED|INDEXING|READY|PARSE_FAILED|INDEX_FAILED
    vector_status: str              # pending|building|done|failed
    kg_status: str                  # pending|building|done|failed
    chunk_count: Optional[int]
    entity_count: Optional[int]
    error_msg: Optional[str]
    created_at: str
    updated_at: str
    ready_for_qa: bool              # status == "READY"

class DocumentListItem(BaseModel):
    doc_id: str
    filename: str
    status: str
    chunk_count: Optional[int]
    entity_count: Optional[int]
    created_at: str

class KGEntity(BaseModel):
    name: str                       # entity_text
    type: str                       # entity_class
    attributes: Dict[str, str]      # key-value 属性
    context_snippet: str            # 原文±200字
    document_id: str

class PassageSource(BaseModel):
    content: str                    # chunk 文本
    section: str                    # section_title
    page: int                       # page_idx
    document_id: str
    chunk_type: str                 # text | table
    entities: List[str]             # json.loads(metadata["entities"])
    char_range: List[int]           # [char_start, char_end]

class QAMeta(BaseModel):
    route: str                      # entity_query|semantic_query|hybrid_query|direct_answer
    rewrite_count: int
    question_used: str              # 最终使用的问题（可能改写过）
    original_question: str
    sufficient: bool
    latency_ms: int

class QASources(BaseModel):
    kg_entities: List[KGEntity]
    passages: List[PassageSource]

class QAResponse(BaseModel):
    answer: str                     # Markdown 格式答案
    meta: QAMeta
    sources: QASources
    session_id: Optional[str]
```

---

## 5. API 接口规范

**Base URL**: `http://localhost:8000/api/v1`

**通用响应头**：
```
Content-Type: application/json; charset=utf-8
X-Request-ID: {uuid}
```

---

### 5.1 文档管理

#### `POST /documents/upload` — 上传文件

**Request**：`multipart/form-data`

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `file` | File | 是 | 文件二进制（支持格式见第1.3节） |
| `enable_ocr` | bool | 否 | 是否启用 OCR（默认 `true`，仅 Precision API 有效） |

**Response 202 Accepted**：
```json
{
  "doc_id": "550e8400-e29b-41d4-a716-446655440000",
  "filename": "技术报告.pdf",
  "file_type": "pdf",
  "status": "PARSING",
  "message": "文件上传成功，MinerU 解析任务已提交"
}
```

**Response 400**（格式不支持）：
```json
{
  "error": "UNSUPPORTED_FORMAT",
  "message": "不支持的文件格式 .mp4，支持格式：pdf/docx/pptx/doc/ppt/xls/xlsx/jpg/jpeg/png/gif/webp/html"
}
```

**Response 413**（文件过大）：
```json
{
  "error": "FILE_TOO_LARGE",
  "message": "文件大小 215MB 超过限制（200MB）"
}
```

---

#### `GET /documents/{doc_id}/status` — 查询文档状态

**Path Params**：`doc_id` — 文档 UUID

**Response 200**：
```json
{
  "doc_id": "550e8400-e29b-41d4-a716-446655440000",
  "filename": "技术报告.pdf",
  "file_type": "pdf",
  "status": "INDEXING",
  "vector_status": "building",
  "kg_status": "done",
  "chunk_count": null,
  "entity_count": 87,
  "error_msg": null,
  "created_at": "2026-04-13T10:00:00Z",
  "updated_at": "2026-04-13T10:04:30Z",
  "ready_for_qa": false
}
```

**Response 200（READY 状态）**：
```json
{
  "doc_id": "550e8400-...",
  "filename": "技术报告.pdf",
  "file_type": "pdf",
  "status": "READY",
  "vector_status": "done",
  "kg_status": "done",
  "chunk_count": 15,
  "entity_count": 130,
  "error_msg": null,
  "created_at": "2026-04-13T10:00:00Z",
  "updated_at": "2026-04-13T10:12:45Z",
  "ready_for_qa": true
}
```

**Response 200（失败状态）**：
```json
{
  "doc_id": "550e8400-...",
  "status": "PARSE_FAILED",
  "error_msg": "MinerU 解析超时（600s），请重新上传",
  "ready_for_qa": false
}
```

**Response 404**：
```json
{ "error": "DOCUMENT_NOT_FOUND", "doc_id": "550e8400-..." }
```

---

#### `GET /documents` — 列出所有文档

**Query Params**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `status` | str | 否 | 过滤状态（READY/PARSING/INDEXING 等） |
| `limit` | int | 否 | 返回数量（默认 20，最大 100） |
| `offset` | int | 否 | 偏移（默认 0） |

**Response 200**：
```json
{
  "total": 5,
  "limit": 20,
  "offset": 0,
  "documents": [
    {
      "doc_id": "550e8400-...",
      "filename": "0.LangChain技术生态介绍.pdf",
      "status": "READY",
      "chunk_count": 15,
      "entity_count": 130,
      "created_at": "2026-04-13T10:00:00Z"
    },
    {
      "doc_id": "661f9511-...",
      "filename": "销售数据统计.xlsx",
      "status": "INDEXING",
      "chunk_count": null,
      "entity_count": null,
      "created_at": "2026-04-13T11:30:00Z"
    }
  ]
}
```

---

#### `DELETE /documents/{doc_id}` — 删除文档

删除范围：SQLite 记录 + uploads/ 文件 + mineru_parser/output/{doc_id}/ + Chroma 对应 chunks + JSONL 中对应实体

**Response 200**：
```json
{
  "message": "文档及其所有索引数据已删除",
  "doc_id": "550e8400-..."
}
```

**Response 400**（PARSING/INDEXING 中不可删除）：
```json
{
  "error": "DOCUMENT_BUSY",
  "message": "文档正在处理中（INDEXING），请等待完成后再删除"
}
```

---

### 5.2 Q&A 问答

#### `POST /qa/query` — 提问

**Request Body**：`application/json`

```json
{
  "question": "LangChain 的核心组件有哪些？",
  "doc_ids": ["550e8400-..."],
  "session_id": null
}
```

| 字段 | 类型 | 必填 | 默认 | 说明 |
|------|------|------|------|------|
| `question` | str | 是 | — | 用户问题，1~500 字符 |
| `doc_ids` | list[str] | 否 | null | 限定检索范围；null = 全库检索 |
| `session_id` | str | 否 | null | 多轮会话 ID（MVP 预留，当前无记忆） |

**Response 200**：
```json
{
  "answer": "## LangChain 核心组件\n\nLangChain 的核心组件主要包括**链（Chain）**和**代理（Agent）**，并通过 **LCEL**（LangChain Expression Language）提供新一代链式调用语法，原生支持流式输出、异步和批处理【来源：实体 LangChain】。\n\n...",
  "meta": {
    "route": "hybrid_query",
    "rewrite_count": 0,
    "question_used": "LangChain 的核心组件有哪些？",
    "original_question": "LangChain 的核心组件有哪些？",
    "sufficient": true,
    "latency_ms": 3240
  },
  "sources": {
    "kg_entities": [
      {
        "name": "LangChain",
        "type": "product",
        "attributes": {
          "type": "元老级Agent开发工具, 大模型开发框架",
          "open_sourced": "2022年10月开源",
          "core_components": "链, 代理"
        },
        "context_snippet": "# LangChain快速入门与Agent开发实战-Part 1\n\n本期公开课，我将为大家详细讲解...",
        "document_id": "0.LangChain技术生态介绍"
      },
      {
        "name": "LangChain Expression Language",
        "type": "concept",
        "attributes": {
          "abbreviation": "LCEL",
          "advantage": "原生支持流式输出/异步/批处理"
        },
        "context_snippet": "在LangChain中，Components是一系列可组合的构建块...",
        "document_id": "0.LangChain技术生态介绍"
      }
    ],
    "passages": [
      {
        "content": "在LangChain中，Components是一系列可组合的构建块，让开发者能够高效地创建AI应用，构建多步骤的工作流程。Components这些模块化组件在LangChain的各个功能中都有着广泛的应用...",
        "section": "4. 组件（Component）",
        "page": 0,
        "document_id": "0.LangChain技术生态介绍",
        "chunk_type": "text",
        "entities": ["LangChain Expression Language", "LCEL"],
        "char_range": [1200, 1750]
      },
      {
        "content": "LlamaIndex，开源于2022年11月，专注于文档处理和RAG（Retrieval-Augmented Generation）...",
        "section": "1. LlamaIndex",
        "page": 0,
        "document_id": "0.LangChain技术生态介绍",
        "chunk_type": "text",
        "entities": ["LlamaIndex"],
        "char_range": [3400, 3900]
      }
    ]
  },
  "session_id": null
}
```

**Response 400（问题为空）**：
```json
{
  "error": "INVALID_QUESTION",
  "message": "问题不能为空，长度需在 1~500 字符之间"
}
```

**Response 400（文档未就绪）**：
```json
{
  "error": "DOCUMENT_NOT_READY",
  "message": "文档 550e8400 当前状态为 INDEXING，请等待索引构建完成后再提问",
  "doc_id": "550e8400-..."
}
```

**Response 400（无可用文档）**：
```json
{
  "error": "NO_READY_DOCUMENTS",
  "message": "当前没有状态为 READY 的文档，请先上传并等待文档处理完成"
}
```

**Response 504（LLM 超时）**：
```json
{
  "error": "LLM_TIMEOUT",
  "message": "问答服务响应超时（30s），请稍后重试"
}
```

---

### 5.3 健康检查

#### `GET /health` — 系统健康状态

**Response 200**：
```json
{
  "status": "ok",
  "timestamp": "2026-04-13T10:00:00Z",
  "components": {
    "database": "ok",
    "chroma_db": "ok",
    "kg_jsonl": "ok",
    "mineru_api": "ok",
    "agentic_rag": "ok"
  },
  "document_stats": {
    "total": 5,
    "ready": 3,
    "indexing": 1,
    "parsing": 0,
    "failed": 1
  }
}
```

**Response 200（部分组件异常）**：
```json
{
  "status": "degraded",
  "components": {
    "database": "ok",
    "chroma_db": "error",
    "kg_jsonl": "ok",
    "mineru_api": "ok",
    "agentic_rag": "error"
  }
}
```

---

## 6. 错误码规范

### 6.1 HTTP 状态码使用规则

| 状态码 | 使用场景 |
|--------|---------|
| 200 | 请求成功 |
| 202 | 已接受（异步任务已提交） |
| 400 | 客户端参数错误（格式/字段/状态不符） |
| 404 | 资源不存在 |
| 413 | 文件过大 |
| 422 | Pydantic 校验失败（FastAPI 自动处理） |
| 500 | 服务端内部错误 |
| 504 | 上游超时（MinerU / LLM） |

### 6.2 业务错误码

| 错误码 | HTTP | 说明 |
|--------|------|------|
| `UNSUPPORTED_FORMAT` | 400 | 上传了不支持的文件格式 |
| `FILE_TOO_LARGE` | 413 | 文件超过大小限制 |
| `DOCUMENT_NOT_FOUND` | 404 | doc_id 不存在 |
| `DOCUMENT_BUSY` | 400 | 文档正在处理中，不可删除 |
| `DOCUMENT_NOT_READY` | 400 | 文档未建索引，不可问答 |
| `NO_READY_DOCUMENTS` | 400 | 无可问答文档 |
| `INVALID_QUESTION` | 400 | 问题为空或超长 |
| `PARSE_FAILED` | 500 | MinerU 解析失败（含 err_msg） |
| `INDEX_FAILED` | 500 | 索引构建失败（含 err_msg） |
| `LLM_TIMEOUT` | 504 | LLM 推理超时 |
| `MINERU_API_ERROR` | 502 | MinerU API 返回错误 |

### 6.3 错误响应统一格式

```json
{
  "error": "ERROR_CODE",
  "message": "人类可读的错误说明",
  "doc_id": "（可选）相关文档 ID",
  "detail": "（可选）技术详情，仅 DEBUG 模式返回"
}
```

---

## 7. 服务层设计

### 7.1 mineru_service.py — MinerU API 封装

**核心职责**：格式路由、文件上传、轮询等待、结果下载解压

```
submit_parse(doc_id, file_path, file_type, enable_ocr)
  ├── file_type in (xls, xlsx)
  │     → POST /api/v1/agent/parse/file       # 获取 file_url
  │     → PUT {file_url}（Content-Length 必填，不加 Content-Type）
  │     → 记录 task_id，status=PARSING
  └── 其他格式
        → POST /api/v4/file-urls/batch         # 获取 presigned_url + batch_id
        → PUT {presigned_url}（同上注意事项）
        → 记录 batch_id，status=PARSING

poll_until_done(doc_id)  # 后台循环，10s/次，最多 600s
  ├── Agent API: GET /api/v1/agent/parse/{task_id}
  │     state=done → 下载 markdown_url → 写入 full.md
  └── Precision API: GET /api/v4/extract-results/batch/{batch_id}
        state=done → 下载 full_zip_url → 解压到 mineru_parser/output/{doc_id}/
  → 失败/超时 → status=PARSE_FAILED，写 error_msg
  → 成功 → status=PARSED → 触发 index_service.build_both(doc_id)
```

**关键注意事项**（来自 mineru-api-spec-v1.0.md）：
- PUT 上传时**不加 Content-Type 请求头**，必须加 `Content-Length`
- Agent API 字段名为 `file_name`/`file_size`（非 `name`/`size`）
- 解析参数（`is_ocr`、`model_version`）需在 Step 1 请求体中提交，不能事后修改

---

### 7.2 index_service.py — 并行索引构建

**核心职责**：并行触发向量索引构建（rag_pipeline）和 KG 抽取（langextract_pipeline）

```
build_both(doc_id)
  → db.update(status=INDEXING, vector_status=building, kg_status=building)
  → asyncio.gather(
       _build_vector_index(doc_id),   # Task A
       _build_kg_index(doc_id)        # Task B
    )
  → 两路均 done → status=READY
  → 任一路 failed → status=INDEX_FAILED，记录 error_msg

_build_vector_index(doc_id)
  → subprocess: python rag_pipeline/pipeline.py build {doc_id}
  → 等待完成，读 stdout 中 chunk_count
  → db.update(vector_status=done, chunk_count=N)

_build_kg_index(doc_id)
  → subprocess: python langextract_pipeline/run_pipeline.py "{doc_id}"
  → 等待完成
  → 统计 langextract_pipeline/output/ 最新 JSONL 中 match_exact 实体数
  → db.update(kg_status=done, entity_count=N)
```

---

### 7.3 qa_service.py — Agentic RAG 查询封装

**核心职责**：加载 agentic_rag 图（单例），执行问答，格式化输出字段

```python
# 全局单例，应用启动时懒加载
_app = None

def get_app():
    global _app
    if _app is None:
        _app = agentic_rag.graph.get_default_graph()
    return _app

def run_query(question: str) -> QAResponse:
    t0 = time.time()
    initial_state = {
        "question": question,
        "original_question": question,
        "route": "", "kg_results": [],
        "passage_results": [], "merged_context": "",
        "sufficient": False, "rewrite_count": 0, "answer": "",
    }
    result = get_app().invoke(initial_state)
    latency = int((time.time() - t0) * 1000)
    return _format_response(result, latency)

def _format_response(result, latency) -> QAResponse:
    # kg_results[i] → KGEntity（字段重命名：entity_text→name, entity_class→type）
    # passage_results[i] → PassageSource（json.loads entities, 提取 char_range）
    # 组装 QAResponse
```

**字段映射（AgentState → API 响应）**：

| AgentState 字段 | API 字段 | 转换 |
|----------------|---------|------|
| `result["answer"]` | `answer` | 直接返回 Markdown 字符串 |
| `result["route"]` | `meta.route` | 直接返回 |
| `result["rewrite_count"]` | `meta.rewrite_count` | 直接返回 |
| `result["question"]` | `meta.question_used` | 直接返回（改写后） |
| `result["original_question"]` | `meta.original_question` | 直接返回 |
| `result["sufficient"]` | `meta.sufficient` | 直接返回 |
| 计算值 | `meta.latency_ms` | `int((time()-t0)*1000)` |
| `result["kg_results"][i]` | `sources.kg_entities[i]` | `entity_text→name, entity_class→type` |
| `result["passage_results"][i]` | `sources.passages[i]` | `json.loads(entities), [char_start,char_end]` |

---

## 8. 配置规范

### 8.1 backend/.env

```bash
# ── MinerU ────────────────────────────────────────────────────────
MINERU_API_TOKEN=sk-xxx
MINERU_BASE_URL=https://mineru.net

# ── LLM（问答引擎）────────────────────────────────────────────────
DASHSCOPE_API_KEY=sk-xxx
LLM_PROVIDER=dashscope              # dashscope | deepseek
LLM_MODEL_ID=qwen3.6-plus
DASHSCOPE_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
DASHSCOPE_EMBEDDING_MODEL=text-embedding-v4

# ── 路径（相对于 backend/，可用绝对路径覆盖）─────────────────────
MINERU_OUTPUT_DIR=../mineru_parser/output
RAG_PIPELINE_DIR=../rag_pipeline
LANGEXTRACT_PIPELINE_DIR=../langextract_pipeline
AGENTIC_RAG_DIR=../agentic_rag
UPLOAD_DIR=./uploads
DB_PATH=./data/jobs.db

# ── 服务参数 ──────────────────────────────────────────────────────
PORT=8000
DEBUG=false
MAX_UPLOAD_SIZE_MB=200              # 文件上传大小限制
POLL_INTERVAL_SEC=10                # MinerU 轮询间隔
POLL_TIMEOUT_SEC=600                # MinerU 最大等待时间
QA_TIMEOUT_SEC=60                   # Q&A 问答超时
```

### 8.2 requirements.txt（核心依赖）

```
fastapi>=0.115.0
uvicorn[standard]>=0.30.0
aiosqlite>=0.20.0
python-multipart>=0.0.9      # multipart/form-data 支持
httpx>=0.27.0                 # 异步 HTTP 客户端（调用 MinerU API）
pydantic>=2.0.0
python-dotenv>=1.0.0
aiofiles>=23.0.0              # 异步文件 I/O

# 间接依赖（来自 agentic_rag 复用）
langgraph
langchain-openai
langchain-chroma
langchain-community
langchain-classic
rank-bm25
chromadb
```

---

## 9. 前端对接指南

### 9.1 文档上传完整交互流程

```
前端操作                          API 调用                         预期响应
──────────────────────────────────────────────────────────────────────────
1. 用户选择文件                   POST /documents/upload           202: {doc_id, status="PARSING"}
2. 开始轮询状态（5s/次）           GET /documents/{doc_id}/status   200: {status, ready_for_qa}
3. 显示进度（解析中/建索引中）     继续轮询...
4. status == READY                停止轮询，启用问答输入框
5. status == *FAILED              显示错误，提示重新上传
```

### 9.2 轮询状态到进度条映射建议

| 后端 status | 前端显示 | 进度条 |
|------------|---------|--------|
| `UPLOADED` | 文件上传成功 | 10% |
| `PARSING` | 文档解析中... | 20~50% |
| `PARSED` | 解析完成，建立索引中... | 55% |
| `INDEXING`（vector building） | 构建向量索引... | 60~70% |
| `INDEXING`（kg building） | 构建知识图谱... | 70~85% |
| `READY` | 就绪，可以提问 ✅ | 100% |
| `PARSE_FAILED` | 解析失败，请重试 ❌ | — |
| `INDEX_FAILED` | 索引构建失败 ❌ | — |

**细化提示**：当 `status=INDEXING` 时，前端可通过 `vector_status` 和 `kg_status` 分别展示两路进度：
- `vector_status=building` + `kg_status=done` → "向量索引构建中，知识图谱已完成"

### 9.3 Q&A 响应渲染建议

| 字段 | 前端渲染方式 |
|------|------------|
| `answer` | Markdown 渲染器（marked.js / react-markdown）|
| `meta.route` | 标签显示路由策略（"知识图谱检索" / "混合检索"）|
| `meta.rewrite_count` | 若 > 0 显示"问题改写 N 次" |
| `sources.kg_entities` | 可展开的实体卡片（name + attributes 表格）|
| `sources.passages` | 可展开的原文片段（section + 文本预览）|
| `meta.latency_ms` | 底部显示耗时（如 "3.2s"）|

### 9.4 前端 Session 预留说明

当前 MVP 版本 `session_id` 字段不生效（每次问答独立）。多轮对话功能预留接口位置：

- 请求时传入 `session_id`（前端自行生成 UUID）
- 响应时 server echo 回 `session_id`
- 后续版本实现：LangGraph checkpointer + 对话历史存储

---

## 10. 非功能性需求

### 10.1 性能基准（MVP 目标）

| 接口 | 目标响应时间 |
|------|------------|
| `POST /documents/upload` | < 3s（含 MinerU 提交） |
| `GET /documents/{id}/status` | < 200ms |
| `GET /documents` | < 500ms |
| `POST /qa/query` | < 15s（含 KG+向量检索+LLM 推理） |
| `GET /health` | < 100ms |

### 10.2 并发处理

- 同时上传文档：支持多个文档并行解析（MinerU 服务端限流，客户端无限制）
- 同时问答：agentic_rag 单例全局共享，LangGraph invoke 线程安全

### 10.3 错误恢复

- **MinerU 解析超时**：记录 PARSE_FAILED，前端重新上传
- **索引构建失败**：可通过 `POST /documents/{doc_id}/reindex`（预留）重试
- **LLM 超时**：返回 504，前端提示重试
- **服务重启恢复**：PARSING/INDEXING 状态的任务在服务启动时自动检测并恢复

### 10.4 日志规范

```
[INFO]  {timestamp} [doc_id={id}] 文件上传完成，类型=pdf，大小=12.4MB
[INFO]  {timestamp} [doc_id={id}] MinerU 任务已提交，batch_id={bid}
[INFO]  {timestamp} [doc_id={id}] MinerU 解析完成，耗时=127s
[INFO]  {timestamp} [doc_id={id}] 向量索引构建完成，chunks=15
[INFO]  {timestamp} [doc_id={id}] KG 索引构建完成，实体=130
[INFO]  {timestamp} [doc_id={id}] 文档状态=READY
[INFO]  {timestamp} [qa] 问题="{q}"，路由=hybrid_query，耗时=3240ms
[WARN]  {timestamp} [doc_id={id}] MinerU 轮询第 45 次，仍在解析中
[ERROR] {timestamp} [doc_id={id}] MinerU 解析失败：{err_msg}
```
