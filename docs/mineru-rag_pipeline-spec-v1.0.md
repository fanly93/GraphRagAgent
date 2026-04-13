# RAG Pipeline 规范文档 v1.0

> 基于 MinerU 解析结果构建结构感知向量+关键词混合检索的 RAG 系统
> 编写日期：2026-04-13 | 最后更新：2026-04-13（切分算法修复 v1.1）
> 实测文档：`0.LangChain技术生态介绍`

---

## 目录

1. [系统架构](#1-系统架构)
2. [输入规范（MinerU 解析结果）](#2-输入规范mineru-解析结果)
3. [执行思路与流程](#3-执行思路与流程)
4. [运行脚本与操作步骤](#4-运行脚本与操作步骤)
5. [关键参数规范](#5-关键参数规范)
6. [实际输出结果规范](#6-实际输出结果规范)
7. [RAG 问答效果实测](#7-rag-问答效果实测)
8. [依赖版本清单](#8-依赖版本清单)
9. [后续扩展：对接 Agentic RAG](#9-后续扩展对接-agentic-rag)

---

## 1. 系统架构

### 1.1 整体数据流

```
MinerU 解析结果
├── *_content_list.json   ← 主要输入（结构化块列表）
└── full.md               ← 辅助输入（降级/字符定位）

          │
          ▼
  structure_splitter.py
  ┌─────────────────────────────────────────────────────────┐
  │  按 text_level 标题边界切分章节                           │
  │  正文段落聚合 → 超出 CHUNK_SIZE 时按句切分               │
  │  短文本（< MIN_CHUNK_SIZE）→ 追加到前一个 chunk，不丢弃  │
  │  table 块独立成 chunk（含 table_caption）                │
  │  image / discarded 块跳过                               │
  │  char_start 顺序游标定位（单调递增，避免重复文本误匹配）   │
  │  可选：从 LangExtract JSONL 注入实体元数据               │
  └─────────────────────────────────────────────────────────┘
          │
          ▼  list[Document]（携带结构化 metadata）
          │
  ┌───────┴────────┐
  ▼                ▼
Chroma             BM25Retriever
(向量库)           (关键词库)
持久化到           内存重建
chroma_db/         (从 bm25_docs.pkl)
          │
          ▼
  EnsembleRetriever（RRF 融合）
  向量权重 0.6 + BM25 权重 0.4
          │
          ▼  list[Document]（top-k 结果）
          │
  LLM（DashScope qwen3.6-plus）
          │
          ▼
  最终答案（含来源引用）
```

### 1.2 模块文件一览

| 文件 | 行数 | 职责 |
|------|------|------|
| `config.py` | 72 | 加载 .env，导出所有配置常量 |
| `structure_splitter.py` | 392 | MinerU content_list.json → 结构感知切分 → list[Document] |
| `embeddings.py` | 46 | Embedding 工厂（DashScope / OpenAI） |
| `indexer.py` | 136 | Chroma build/load + BM25 pickle 缓存 |
| `retriever.py` | 93 | EnsembleRetriever 混合检索 |
| `llm_provider.py` | 37 | LLM 工厂（DashScope / DeepSeek） |
| `pipeline.py` | 186 | CLI 入口（build / query / stats） |

---

## 2. 输入规范（MinerU 解析结果）

### 2.1 必要文件（RAG 构建实际读取）

| 文件 | 是否必须 | 用途 |
|------|---------|------|
| `*_content_list.json` | **必须** | 核心输入，提供结构化块（type/text/text_level/table_body/page_idx） |
| `full.md` | 辅助 | 两种情况使用：① 无 content_list 时作为降级来源；② char_start 字符偏移定位 |

### 2.2 不需要的文件（RAG 构建不读取）

| 文件 | 原因 |
|------|------|
| `layout.json` | MinerU 内部中间产物，已被 content_list.json 提炼 |
| `*_origin.pdf` | 原始文件，解析已完成 |
| `images/` | 图片块（type=image）在切分时被跳过 |

### 2.3 content_list.json 关键字段

```json
[
  {
    "type": "text",           // text | table | image | discarded | equation
    "text": "段落内容",        // 文本内容（text 类型）
    "text_level": 1,          // 标题层级 1~6（仅标题块有此字段）
    "page_idx": 0,            // 页码（0-based）
    "table_body": "<table>",  // HTML 表格（table 类型）
    "table_caption": ["标题"], // 表格标题（list[str]）
    "img_path": "images/xxx.jpg", // 图片路径（image 类型）
    "bbox": [x0, y0, x1, y1]  // 页面坐标（归一化 0-1000）
  }
]
```

### 2.4 各类文档有效性评估

| 文档类型 | content_list | 有效正文 | 建议 |
|---------|-------------|---------|------|
| PDF/Word 文档 | ✅ | 有文本+表格块 | 推荐，结构感知效果最佳 |
| 图片类文档 | ✅ | 0字（仅 image 块） | 跳过，无可检索文本 |
| Excel（Agent API） | ❌ | 仅 full.md | 降级切分，效果较弱 |
| 重复解析的相同文档 | ✅ | 重复内容 | 用 doc_filter 排除其中一个 |

---

## 3. 执行思路与流程

### 3.1 结构感知切分算法（structure_splitter.py）

```
全局状态：
  search_cursor = 0   ← char_start 顺序游标，单调递增

遍历 content_list.json 的每个 block：

  if type == "discarded" or "image":
      → 跳过

  if type == "text" and has text_level:
      → 刷新当前文本缓冲区（_flush_buffer）
      → 更新 current_section_title / current_section_level
      → 标题本身不独立成 chunk（太短）

  if type == "text" (正文):
      → 追加到 text_buffer
      → 若 buffer 总长 >= CHUNK_SIZE：提前 flush

  if type == "table":
      → 刷新文本缓冲区
      → 拼接 "表格：{caption}\n{table_body}" 独立成 chunk
      → 顺序游标定位 char_start（search_cursor 向前推进）

_flush_buffer() 逻辑：
  - 合并 buffer 为 combined text，清空 text_buffer
  - 若 len(combined) < MIN_CHUNK_SIZE：
      → 调用 _append_to_last(combined)，追加到上一个 Document   ← [修复一/三]
      → return（不单独成 chunk）
  - 顺序游标定位 char_start：                                    ← [修复二]
      needle = combined 首行前 40 字
      char_start = full_text.find(needle, search_cursor)
      search_cursor = char_start + 1
  - 若 len <= CHUNK_SIZE：整体作为一个 chunk
  - 若 len > CHUNK_SIZE：按句子边界（。！？\n）递归切分，保留 overlap

_append_to_last(text)：
  - 取 documents[-1]，拼接 "\n" + text 到 page_content
  - 更新 char_end 和 entities（重新按新范围匹配 LangExtract 实体）
```

### 3.2 实体注入（可选）

```
若 LANGEXTRACT_OUTPUT_DIR 中存在对应文档的 .jsonl 文件：
  → 加载 match_exact 状态的 extraction（grounded 实体）
  → 对每个 chunk 按 char_interval 坐标匹配
  → 将实体名称和类型序列化为 JSON 字符串注入 metadata
```

### 3.3 索引构建策略

| 索引 | 实现 | 持久化 |
|------|------|--------|
| 向量索引 | Chroma（HNSW） | `chroma_db/` 目录（SQLite + 二进制文件） |
| 关键词索引 | BM25Retriever（rank-bm25） | `chroma_db/bm25_docs.pkl`（pickle 序列化） |

**BM25 缓存设计说明**：BM25 是内存检索器，每次 load 时从 pkl 文件反序列化 Document 列表重建，无需重新调用 Embedding API。

### 3.4 Hybrid 检索融合（EnsembleRetriever）

采用 **Reciprocal Rank Fusion (RRF)** 算法合并两路结果：

```
score_rrf(doc) = Σ [ weight_i / (k + rank_i) ]

其中：
  k = 60（RRF 平滑常数）
  weight_0 = 0.6（向量检索，命中语义相近内容）
  weight_1 = 0.4（BM25，命中专有名词/精确关键词）
```

---

## 4. 运行脚本与操作步骤

### 4.1 脚本路径

```
/Users/tanglin/VibeCoding/GraphRagAgent/rag_pipeline/
├── pipeline.py          ← 主入口（CLI）
├── .env                 ← 环境配置（含 API Key）
├── .venv/               ← 独立虚拟环境
└── chroma_db/           ← 索引持久化目录
```

### 4.2 环境激活

```bash
cd /Users/tanglin/VibeCoding/GraphRagAgent/rag_pipeline
source .venv/bin/activate
```

> **重要**：此 `.venv` 独立于 `langextract_pipeline` 和 `mineru_parser`，不要混用。

### 4.3 完整操作流程

#### Step 1：配置 .env

```bash
# 必填
DASHSCOPE_API_KEY=sk-xxxx
DASHSCOPE_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
DASHSCOPE_EMBEDDING_MODEL=text-embedding-v4

LLM_PROVIDER=dashscope
LLM_MODEL_ID=qwen3.6-plus
```

#### Step 2：构建索引

```bash
# 索引指定文档（推荐，避免索引无效文档）
python pipeline.py build "0.LangChain技术生态介绍"

# 索引全部文档
python pipeline.py build

# 强制重建（清空旧索引）
python pipeline.py build --force

# 同时指定多个文档
python pipeline.py build "0.LangChain技术生态介绍" "数组"
```

**实测输出（`0.LangChain技术生态介绍`）：**
```
[1/3] 结构感知文本切分
  MinerU 目录：.../mineru_parser/output
  chunk_size=800  overlap=100
  [切分] 0.LangChain技术生态介绍 → 15 chunks

[2/3] 构建向量索引（Chroma + BM25）
  [Embedding] DashScope  model=text-embedding-v4
  [索引] 向量化 15 个 chunks → Chroma (chroma_db/)
  [索引] BM25 语料已缓存 (15 docs)

[3/3] 索引摘要
  状态：ready
  总 chunks：15
  文档列表：['0.LangChain技术生态介绍']
  类型分布：{'text': 13, 'table': 2}
```

#### Step 3：查询

```bash
python pipeline.py query "LangChain是什么？"
python pipeline.py query "LangGraph有哪些特性？" --no-sources
```

#### Step 4：查看索引统计

```bash
python pipeline.py stats
```

---

## 5. 关键参数规范

### 5.1 .env 完整参数表

| 参数 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `EMBEDDING_PROVIDER` | 是 | `dashscope` | `dashscope` \| `openai` |
| `DASHSCOPE_API_KEY` | 是* | — | DashScope API Key |
| `DASHSCOPE_BASE_URL` | 否 | `https://dashscope.aliyuncs.com/compatible-mode/v1` | DashScope 接口地址 |
| `DASHSCOPE_EMBEDDING_MODEL` | 否 | `text-embedding-v3` | Embedding 模型名 |
| `OPENAI_API_KEY` | 是** | — | OpenAI API Key |
| `LLM_PROVIDER` | 是 | `dashscope` | `dashscope` \| `deepseek` |
| `LLM_MODEL_ID` | 是 | `qwen-plus` | LLM 模型名 |
| `DEEPSEEK_API_KEY` | 是*** | — | DeepSeek API Key |
| `CHUNK_SIZE` | 否 | `500` | chunk 目标字符数（实测用 800） |
| `CHUNK_OVERLAP` | 否 | `80` | 相邻 chunk 重叠字符数（实测用 100） |
| `MIN_CHUNK_SIZE` | 否 | `50` | 小于此值的 chunk 追加到前一个 Document（实测用 80） |
| `CHROMA_PERSIST_DIR` | 否 | `./chroma_db` | 向量库持久化目录 |
| `VECTOR_WEIGHT` | 否 | `0.6` | 向量检索权重（与 BM25_WEIGHT 之和=1） |
| `BM25_WEIGHT` | 否 | `0.4` | BM25 关键词检索权重 |
| `RETRIEVAL_TOP_K` | 否 | `4` | 每路检索返回文档数（实测用 5） |
| `MINERU_OUTPUT_DIR` | 否 | `../mineru_parser/output` | MinerU 解析结果根目录 |
| `LANGEXTRACT_OUTPUT_DIR` | 否 | `../langextract_pipeline/output` | LangExtract JSONL 目录 |

> *当 `EMBEDDING_PROVIDER=dashscope` 时必填
> **当 `EMBEDDING_PROVIDER=openai` 时必填
> ***当 `LLM_PROVIDER=deepseek` 时必填

### 5.2 DashScope Embedding 特殊配置

DashScope 与标准 OpenAI Embedding API 的两处兼容差异，**必须**在 `embeddings.py` 中设置：

```python
OpenAIEmbeddings(
    check_embedding_ctx_length=False,  # DashScope 不支持 tokenized 批量输入
    chunk_size=10,                     # DashScope 单批最多 10 条文本
)
```

### 5.3 切分参数调优建议

| 参数 | 偏小效果 | 偏大效果 | 推荐范围 |
|------|---------|---------|---------|
| `CHUNK_SIZE` | chunk 数量多，语义完整性差 | chunk 数量少，召回精度低 | 500~1000 字符 |
| `CHUNK_OVERLAP` | 跨 chunk 信息断裂 | 内容冗余，索引膨胀 | CHUNK_SIZE 的 10%~15% |
| `RETRIEVAL_TOP_K` | 召回不足，漏掉相关段落 | 噪声多，LLM 上下文过长 | 4~6 |
| `VECTOR_WEIGHT` | 关键词精确匹配权重低 | 语义检索主导，术语召回弱 | 0.5~0.7 |

---

## 6. 实际输出结果规范

### 6.1 Chroma 向量库（持久化）

**存储路径：** `rag_pipeline/chroma_db/`

```
chroma_db/
├── {uuid}/                     ← HNSW 向量索引文件（自动生成 UUID）
│   ├── data_level0.bin         ← 向量数据（HNSW 图层 0）
│   ├── header.bin              ← 索引元信息
│   ├── length.bin              ← 向量维度信息
│   └── link_lists.bin          ← HNSW 链接列表
├── bm25_docs.pkl               ← BM25 语料（pickle 序列化 Document 列表）
└── chroma.sqlite3              ← 元数据存储（文档 ID、metadata 等）
```

**实测数据：**
- 文件总大小：912 KB
- Collection 名：`graphrag_docs`
- Embedding 维度：**1024**（text-embedding-v4 默认维度）

### 6.2 Document（chunk）数据结构

每个切分后的 Document 包含以下字段：

**page_content（文本内容）：**
```
# 文本 chunk 示例
本期公开课，我将为大家详细讲解元老级Agent开发工具——LangChain。
LangChain可以称之为自2022年底大模型技术爆火以来的第一个真正意义上的...

# 表格 chunk 示例
表格：LangChain 核心模块分类
<table><tr><td>模块类别</td><td>示例功能</td></tr>...</table>
```

**metadata 字段规范：**

| 字段 | 类型 | 示例值 | 说明 |
|------|------|--------|------|
| `document_id` | str | `"0.LangChain技术生态介绍"` | MinerU 输出子目录名 |
| `section_title` | str | `"1. GPT-3时代下第一代大模型开发工具"` | 所属章节标题 |
| `section_level` | int | `1` | 标题层级（1~6，0=无标题） |
| `page_idx` | int | `0` | 原始页码（0-based） |
| `char_start` | int | `58` | 在 full.md 中的字符起始偏移 |
| `char_end` | int | `666` | 在 full.md 中的字符结束偏移 |
| `chunk_type` | str | `"text"` 或 `"table"` | chunk 类型 |
| `table_caption` | str | `"LangChain 核心模块"` | 仅 table chunk 有此字段 |
| `entities` | str(JSON) | `'["LangChain", "Python"]'` | JSON 序列化实体名称列表 |
| `entity_types` | str(JSON) | `'["technology", "technology"]'` | JSON 序列化实体类型列表 |
| `source` | str | `".../output/0.LangChain技术生态介绍"` | 原始目录绝对路径 |

> **注意**：`entities` 和 `entity_types` 序列化为 JSON 字符串，而非原生 list，原因是 Chroma 不允许 metadata 中存在空列表（`[]`）。读取时需 `json.loads(meta["entities"])`。

### 6.3 实测 chunk 分布（`0.LangChain技术生态介绍`，切分算法修复后）

| # | 章节标题 | 页码 | 类型 | 字符数 | 实体数 |
|---|---------|------|------|--------|--------|
| 01 | 1. GPT-3时代下第一代大模型开发工具 | 0 | text | 568 | 3 |
| 02 | 2. 备受争议的工具功能 | 0 | text | 714 | 2 |
| 03 | 1."太臃肿，依赖太多，维护复杂" | 1 | text | 514 | 1 |
| 04 | 2."抽象混乱、名称不一致，调试困难" | 1 | text | 397 | 0 |
| 05 | 3."文档混乱、更新跟不上代码" | 2 | text | 381 | 2 |
| 06 | 3. 更加适用于当前Agent开发的LangChain工具生态 | 2 | text | 184 | 0 |
| 07 | 3. 更加适用于当前Agent开发的LangChain工具生态 | 2 | **table** | 957 | 9 |
| 08 | 3. 更加适用于当前Agent开发的LangChain工具生态 | 2 | text | 244 | 1 |
| 09 | LangGraph | 3 | text | 472 | 3 |
| 10 | Find failures fast with agent observability | 3 | text | 658 | 2 |
| 11 | LangChain Sandbox: Run untrusted Python... | 5 | text | 478 | 2 |
| 12 | 4. 当下大模型开发人员必备技能：LangChain | 5 | text | 325 | 0 |
| 13 | 职位详情 | 6 | **table** | 753 | 3 |
| 14 | LangGraph; | 6 | text | 241 | 0 |
| 15 | Gemini Fullstack LangGraph Quickstart | 7 | text | 617 | 2 |

**统计摘要：**
- 总 chunks：15（text: 13，table: 2）
- 平均 chunk 字符数：500
- 最长 chunk：957字（表格 chunk，包含 HTML）
- 最短 chunk：184字（超过 MIN_CHUNK_SIZE=80 保留）
- 实体覆盖：11/15 个 chunk 有 LangExtract 实体注入
- char_start 单调递增：13/13 文本 chunk 全部通过验证（修复前有 1 个偏差）
- 关键短文本保留：修复前 17 个有价值短块被丢弃，修复后全部追加到相邻 chunk

### 6.4 stats 命令输出格式

```json
{
  "status": "ready",
  "total_chunks": 15,
  "documents": ["0.LangChain技术生态介绍"],
  "chunk_types": {
    "text": 13,
    "table": 2
  },
  "chroma_count": 15
}
```

`status` 取值：`"ready"` | `"not_built"` | `"error"`

---

## 7. RAG 问答效果实测

### 测试配置

- Embedding：DashScope `text-embedding-v4`（1024维）
- LLM：DashScope `qwen3.6-plus`
- 检索：Hybrid（向量 0.6 + BM25 0.4），top_k=5，实际召回 9 条（RRF 融合去重后）

---

### 问题 1：LangChain的发展历程是什么？它经历了哪些重要阶段？

**最相关 3 个来源：**

| 排名 | 章节 | 页码 | 类型 |
|------|------|------|------|
| 1 | `4. 当下大模型开发人员必备技能：LangChain` | p.5 | text |
| 2 | `1. GPT-3时代下第一代大模型开发工具` | p.0 | text（实体：2022年10月开源, Python/TS, 链）|
| 3 | `3. 更加适用于当前Agent开发的LangChain工具生态` | p.2 | text（实体：2023年下半年开源LangGraph）|

**答案摘要：**
LangChain 经历三个阶段：① 2022年10月开源，快速成为最受欢迎大模型框架；② 2023年下半年因 GPT 原生 Function calling 崛起而饱受争议；③ 大刀阔斧改革，推出 LangGraph，生态成熟为企业级工具链。

---

### 问题 2：LangGraph是什么？它和LangChain是什么关系？

**最相关 3 个来源：**

| 排名 | 章节 | 页码 | 类型 |
|------|------|------|------|
| 1 | `LangGraph;` | p.6 | text |
| 2 | `3. 更加适用于当前Agent开发的LangChain工具生态` | p.2 | text（实体：2023年下半年开源LangGraph）|
| 3 | `LangGraph` | p.3 | text（实体：Klarna, Replit, Elastic）|

**答案摘要：**
LangGraph 是 2023 年下半年开源的图结构 Multi-Agent 编排框架，用于构建有状态（stateful）的长期运行智能体。**关系**：LangGraph 是 LangChain 的高层次封装，底层完全依赖 LangChain 实现，是 LangChain 家族最核心的 Agent 开发框架。

---

### 问题 3：LangChain目前有哪些工具生态？适合哪些应用场景？

**最相关 3 个来源：**

| 排名 | 章节 | 页码 | 类型 |
|------|------|------|------|
| 1 | `4. 当下大模型开发人员必备技能：LangChain` | p.5 | text |
| 2 | `1. GPT-3时代下第一代大模型开发工具` | p.0 | text |
| 3 | `3. 更加适用于当前Agent开发的LangChain工具生态` | p.2 | text（实体：2023年下半年开源LangGraph）|

**答案摘要（工具生态）：**
- **LangChain**：核心框架，"积木工厂"
- **LangGraph**：图结构 Multi-Agent 工作流编排
- **LangSmith**：Agent 可观测性，Step-by-step 追踪调试
- **LangFlow**：可视化低代码开发（拖拽式）
- **LangChain Sandbox**：基于 Pyodide/WebAssembly 的安全代码执行沙盒

**适合场景**：小规模实验 → 大规模商业化部署 / 纯代码 → 低代码 / Multi-Agent 协同 / Deep Research 应用

### 7.1 效果评估

| 维度 | 评价 | 说明 |
|------|------|------|
| 召回准确性 | 良好 | 3个问题均命中对应章节 |
| 来源引用 | 完整 | 每个回答均含文档名+章节标注 |
| 结构感知效果 | 有效 | 各章节独立成段，不跨章节混合 |
| 实体注入效果 | 有效 | 11/15 chunk 含 LangExtract 实体（如 LangSmith、LangFlow、A2A） |
| 短文本保留 | 已修复 | 原被丢弃的"A2A协议"、"积木工厂"、"大规模流失"等内容现已可被检索 |
| 噪声控制 | 待优化 | 部分问题召回中出现低相关表格 chunk，可适当降低 BM25 权重 |

### 7.2 切分算法修复验证（2026-04-13）

针对分析发现的三个问题进行了修复，修复后验证结果：

| 问题 | 修复前 | 修复后 | 验证结果 |
|------|--------|--------|---------|
| 短文本丢失（问题一） | 53个正文块中17个有价值短块被静默丢弃 | `_append_to_last()` 追加到前一个 Document | ✅ 5/5 关键短文本可被检索 |
| char_start 定位偏差（问题二） | 从头 `find()`，1/13 chunk 出现定位偏差 | 顺序游标 `find(needle, cursor)`，游标单调递增 | ✅ 13/13 chunk 单调递增 |
| 短章节碎片（问题三） | 短节内容可能产生 <80字孤立 chunk | 与问题一共用 `_append_to_last()` 合并逻辑 | ✅ 无独立短 chunk |

**修复后验证的关键短文本（修复前丢失，修复后可检索）：**
- "在经历了短暂的阵痛后，LangChain果断进行了大刀阔斧的改革..." → 归入章节 3
- "同时，LangChain也是最早官宣支持谷歌A2A技术协议的开发框架..." → 归入 LangChain Sandbox 章节
- "LangFlow功能更加完善，并且没有任何商业化的计划..." → 归入 Find failures fast 章节
- "而这也使得在某个时间段，LangChain的开发者大规模流失" → 归入章节 3."文档混乱"

---

## 8. 依赖版本清单

**Python 版本：** 3.13

| 包名 | 版本 | 用途 |
|------|------|------|
| `langchain` | 1.2.15 | 核心框架 |
| `langchain-openai` | 1.1.12 | OpenAI / DashScope Embedding + LLM |
| `langchain-chroma` | 1.1.0 | Chroma 向量库集成 |
| `langchain-community` | 0.4.1 | BM25Retriever |
| `langchain-classic` | 1.0.3 | EnsembleRetriever（LangChain 1.x 拆分到此包） |
| `langchain-text-splitters` | — | RecursiveCharacterTextSplitter（降级用） |
| `chromadb` | 1.5.7 | 向量库 |
| `rank-bm25` | 0.2.2 | BM25 算法实现 |
| `python-dotenv` | — | .env 加载 |

> **注意**：在 LangChain 1.x 中，`EnsembleRetriever` 从 `langchain.retrievers` 移至 `langchain_classic.retrievers`，需从 `langchain-classic` 包导入。

安装命令：
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

## 9. 对接 Agentic RAG（已实现，2026-04-13）

> 完整规范见：`docs/agentic-rag-pipeline-spec-v1.0.md`

### 9.1 当前 RAG Pipeline 暴露的接口

Agentic RAG（`agentic_rag/`）通过 sys.path 注入直接调用 rag_pipeline 模块：

```python
# agentic_rag/config.py 在导入时注入 sys.path
sys.path.insert(0, str(RAG_PIPELINE_DIR.resolve()))

# agentic_rag/retrievers/hybrid_retriever.py
from retriever import create_hybrid_retriever   # 直接 import rag_pipeline 模块

retriever = create_hybrid_retriever(top_k=5)
docs = retriever.invoke(query)   # 返回 list[Document]

# metadata 关键字段（详见第6.2节）
doc.page_content                  # 文本内容
doc.metadata["document_id"]       # 文档ID
doc.metadata["section_title"]     # 章节标题
doc.metadata["page_idx"]          # 页码
doc.metadata["chunk_type"]        # text | table
doc.metadata["entities"]          # JSON字符串，需 json.loads() 解析
doc.metadata["char_start"]        # 字符偏移（对应 full.md）
```

**重要**：`agentic_rag/config.py` 必须包含 `VECTOR_WEIGHT` 和 `BM25_WEIGHT` 字段，否则 `rag_pipeline/retriever.py` 在 `import config` 时因字段缺失报 `AttributeError`。

### 9.2 已实现的 Agentic RAG 架构（LangGraph 5 节点）

```
route_question ──→ retrieve ──→ grade_documents ──充分──→ generate_answer ──→ END
                      ↑               │
                      │             不足
                      │               ↓
                      └────── rewrite_question（最多 2 次）
```

**路由策略**：`entity_query` / `semantic_query` / `hybrid_query` / `direct_answer`

**双路检索**：KGRetriever（BM25 over LangExtract JSONL 实体）+ HybridRetriever（向量+BM25 段落）

### 9.3 实测性能（3 问题 MVP 验证）

| 维度 | 结果 |
|------|------|
| 路由准确率 | 3/3（100%） |
| 首次检索充分率 | 3/3（无需改写） |
| KG 实体召回 | 精准命中，细粒度实体（追踪功能、评测）也被命中 |
| 段落召回 | 目标章节均排前3，RRF 融合去重后实际返回 9 条 |
| 答案质量 | 3/3 含对比表格+来源引用，结构清晰，信息准确 |

### 9.4 后续扩展方向

| 功能 | 状态 | 说明 |
|------|------|------|
| LangGraph 5节点图 | ✅ 已实现 | `agentic_rag/graph.py` |
| 问题路由（4分类） | ✅ 已实现 | `nodes/router.py` |
| 双路混合检索 | ✅ 已实现 | `nodes/retriever.py` |
| 充分性评估 | ✅ 已实现 | `nodes/grader.py` |
| 问题改写（最多2次） | ✅ 已实现 | `nodes/rewriter.py` |
| 融合生成（含来源引用） | ✅ 已实现 | `nodes/generator.py` |
| 多轮对话记忆 | 待实现 | LangGraph checkpointer |
| 流式输出（streaming） | 待实现 | LangGraph stream() |
| 前端 API 接口（FastAPI） | 待实现 | 基于第6节输出规范 |
