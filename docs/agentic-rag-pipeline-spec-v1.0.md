# Agentic RAG Pipeline 规范文档 v1.0

> 基于 LangGraph 5 节点图，融合 KG 检索（LangExtract）+ 混合向量检索（rag_pipeline）  
> 编写日期：2026-04-13  
> 实测文档：`0.LangChain技术生态介绍`（KG 实体 130 个，向量 chunks 15 个）  
> 模型：`qwen3.6-plus`（DashScope OpenAI-compatible 接口）

---

## 目录

1. [系统定位与架构](#1-系统定位与架构)
2. [实现思路](#2-实现思路)
3. [5 节点图执行流程](#3-5-节点图执行流程)
4. [运行脚本与操作步骤](#4-运行脚本与操作步骤)
5. [输入规范（AgentState）](#5-输入规范agentstate)
6. [输出规范（前后端联调字段）](#6-输出规范前后端联调字段)
7. [路由策略规范](#7-路由策略规范)
8. [检索结果规范](#8-检索结果规范)
9. [关键参数规范](#9-关键参数规范)
10. [MVP 实测结果（3 问题）](#10-mvp-实测结果3-问题)
11. [依赖版本清单](#11-依赖版本清单)
12. [与上游 Pipeline 的对接关系](#12-与上游-pipeline-的对接关系)

---

## 1. 系统定位与架构

### 1.1 系统定位

Agentic RAG 是整个 GraphRAG Agent 项目的**查询层**，负责将用户问题转化为最终答案。它是以下两条上游 pipeline 的**消费端**：

| 上游 Pipeline | 产物 | Agentic RAG 消费方式 |
|--------------|------|---------------------|
| `rag_pipeline`（向量+BM25 混合检索） | `chroma_db/`（Chroma 向量库 + BM25 pkl） | `hybrid_retriever.py` 调用 `create_hybrid_retriever()` |
| `langextract_pipeline`（LangExtract KG 抽取） | `output/kg_extraction_*.jsonl` | `kg_retriever.py` 加载 JSONL，BM25 索引实体 |

### 1.2 整体架构

```
用户问题（自然语言）
        │
        ▼
┌───────────────────────────────────────────────────────────────┐
│                   Agentic RAG（LangGraph）                     │
│                                                               │
│  Node 1: route_question                                       │
│    └── LLM 分类路由 → entity_query / semantic_query /         │
│                        hybrid_query / direct_answer           │
│                                                               │
│  Node 2: retrieve                                             │
│    ├── entity_query  → KGRetriever（BM25 over JSONL 实体）    │
│    ├── semantic_query → HybridRetriever（向量+BM25 段落）      │
│    ├── hybrid_query  → KGRetriever + HybridRetriever 并行     │
│    └── direct_answer → 跳过检索                               │
│                                                               │
│  Node 3: grade_documents                                      │
│    └── LLM 评估 merged_context 对 question 的充分性           │
│         → {"sufficient": bool, "reason": str}                 │
│                                                               │
│  Node 4: rewrite_question（条件执行）                          │
│    └── 检索不足时改写问题，递增 rewrite_count                  │
│         最多 MAX_REWRITE_ATTEMPTS=2 次                        │
│                                                               │
│  Node 5: generate_answer                                      │
│    └── 融合 KG 实体卡片 + 段落内容 → LLM 生成最终答案         │
│                                                               │
└───────────────────────────────────────────────────────────────┘
        │
        ▼
最终答案（含 KG 实体引用 + 段落来源标注）
```

### 1.3 图拓扑结构

```
route_question ──→ retrieve ──→ grade_documents ──充分──→ generate_answer ──→ END
                      ↑               │
                      │             不足
                      │               ↓
                      └────── rewrite_question
                        （最多 MAX_REWRITE_ATTEMPTS 次）
```

### 1.4 模块文件一览

```
agentic_rag/
├── config.py                  # 配置加载（含 sys.path 注入 rag_pipeline）
├── state.py                   # AgentState TypedDict（9 个字段）
├── prompts.py                 # 5 个 Prompt 模板
├── graph.py                   # LangGraph StateGraph 构建与编译
├── pipeline.py                # CLI 入口（交互 / 单次查询）
├── nodes/
│   ├── router.py              # Node 1: route_question
│   ├── retriever.py           # Node 2: retrieve（4 策略）
│   ├── grader.py              # Node 3: grade_documents
│   ├── rewriter.py            # Node 4: rewrite_question + should_rewrite
│   └── generator.py           # Node 5: generate_answer
└── retrievers/
    ├── kg_retriever.py        # KGRetriever（BM25 over LangExtract JSONL）
    └── hybrid_retriever.py    # 包装 rag_pipeline EnsembleRetriever
```

---

## 2. 实现思路

### 2.1 双路检索融合设计

Agentic RAG 的核心创新是**两种完全不同粒度的检索**并行融合：

| 检索路径 | 数据源 | 检索方式 | 返回粒度 | 优势 |
|---------|--------|---------|---------|------|
| **KG 检索** | LangExtract JSONL（实体+属性） | BM25 over 实体文本 | 单一实体 + 原文上下文±200字 | 精确，有结构化属性 |
| **段落检索** | Chroma + BM25（chunk） | EnsembleRetriever（RRF） | 完整段落 chunk（500~1000字） | 丰富，语义连续 |

两路结果在 `merged_context` 中拼接，统一送入 LLM：

```
=== 知识图谱实体 ===
[实体卡片 1] 实体名 (类型)
  属性: key=value | key=value
  原文片段: ...±200字上下文...

=== 文档段落 ===
[1] 文档：xxx  章节：xxx（页码 N）
    相关实体：entity1, entity2
    {chunk 内容}
```

### 2.2 路由器设计

问题路由是 Agentic RAG 的流量入口，4 种路由对应不同检索策略：

```
ROUTE_PROMPT 分类规则：
  - entity_query:   问特定实体的属性/功能（"LangSmith 是什么？"）
  - semantic_query: 问概念/原理/流程（"RAG 的工作原理？"）
  - hybrid_query:   问比较/综合/多实体（"LangChain 和 LlamaIndex 的区别？"）
  - direct_answer:  通用知识/闲聊，不需要检索（"你好"）
```

### 2.3 充分性评估与改写循环

```python
# grader.py 解析 LLM 输出
{"sufficient": true/false, "reason": "检索内容覆盖率..."}

# rewriter.py 条件边
def should_rewrite(state):
    if state["sufficient"]:          return "generate"
    if state["rewrite_count"] >= 2:  return "generate"  # 强制结束
    return "rewrite"
```

### 2.4 配置隔离：sys.path 注入

`agentic_rag/config.py` 在导入时将 `rag_pipeline/` 注入 `sys.path`，使得 rag_pipeline 的所有模块（`indexer`、`retriever`、`embeddings`）可以直接 `import` 复用，无需复制代码。

**关键约束**：`agentic_rag/config.py` 必须包含 rag_pipeline 需要的所有 config 字段（`VECTOR_WEIGHT`、`BM25_WEIGHT` 等），否则 rag_pipeline 模块 `import config` 时会因字段缺失报错。

---

## 3. 5 节点图执行流程

### Node 1: route_question

**输入**：`state["question"]`

**执行**：
```python
prompt = ROUTE_PROMPT.format(question=question)
response = llm.invoke(prompt)
# 从 LLM 回复中提取路由类型（支持 JSON 解析和正则兜底）
route = parse_route(response.content)
```

**输出**：`state["route"]` ∈ `{entity_query, semantic_query, hybrid_query, direct_answer}`

**Prompt 核心规则**：
- 识别到具体实体名词 + 属性查询 → `entity_query`
- 识别到概念/原理 → `semantic_query`
- 比较/综合多个主题 → `hybrid_query`
- 闲聊/通用知识 → `direct_answer`

---

### Node 2: retrieve

**输入**：`state["question"]`, `state["route"]`

**执行策略矩阵**：

| route | KG 检索 | 段落检索 |
|-------|---------|---------|
| `entity_query` | ✅ `kg_retriever.retrieve(q, top_k=5)` | ❌ |
| `semantic_query` | ❌ | ✅ `retrieve_passages(q, top_k=5)` |
| `hybrid_query` | ✅ | ✅（两路并行） |
| `direct_answer` | ❌ | ❌（跳过，直接生成） |

**KGRetriever 实现**：
```python
# 从所有 JSONL 文件中加载 match_exact 实体，构建 BM25 索引
# 检索时：BM25 over (entity_text + attribute values)
# 返回：含 context_snippet（原文±200字）的实体卡片列表
```

**HybridRetriever 实现**：
```python
# 调用 rag_pipeline/retriever.py 的 create_hybrid_retriever()
# EnsembleRetriever：Chroma 向量(0.6) + BM25(0.4)，RRF 融合
# 返回：list[Document]（含 metadata: section_title/entities/char_start 等）
```

**输出**：`state["kg_results"]`, `state["passage_results"]`, `state["merged_context"]`

---

### Node 3: grade_documents

**输入**：`state["question"]`, `state["merged_context"]`

**执行**：
```python
# 截断 context 前 2000 字送 LLM 评估
prompt = GRADE_PROMPT.format(question=question, context=context[:2000])
response = llm.invoke(prompt)
# 解析 JSON：{"sufficient": bool, "reason": str}
```

**特殊处理**：
- `route == "direct_answer"` → 跳过，直接设 `sufficient=True`
- 解析失败 → 视为充分（防止死循环）

**输出**：`state["sufficient"]`, `state["_grade_reason"]`

---

### Node 4: rewrite_question（条件执行）

**触发条件**：`sufficient=False` 且 `rewrite_count < MAX_REWRITE_ATTEMPTS`

**执行**：
```python
prompt = REWRITE_PROMPT.format(question=question, reason=reason)
response = llm.invoke(prompt)
new_question = response.content.strip()
```

**输出**：`state["question"]`（改写后），`state["rewrite_count"]`（+1）

**条件边 `should_rewrite(state)` 返回值**：
- `"generate"`：sufficient=True 或 rewrite_count >= MAX_REWRITE_ATTEMPTS
- `"rewrite"`：继续改写

---

### Node 5: generate_answer

**输入**：`state["question"]`, `state["route"]`, `state["kg_results"]`, `state["passage_results"]`

**执行**：
```python
if route == "direct_answer":
    prompt = DIRECT_ANSWER_PROMPT.format(question=question)
else:
    kg_context = kg_retriever.format_for_prompt(kg_results)
    passage_context = format_passages_for_prompt(passage_results)
    prompt = GENERATE_PROMPT.format(
        kg_context=kg_context,
        passage_context=passage_context,
        question=question,
    )
response = llm.invoke(prompt)
```

**生成规则（GENERATE_PROMPT 约束）**：
- 优先引用 KG 实体的结构化属性（精确信息）
- 段落内容提供背景和上下文
- 引用格式：`[来源：实体 X]` 或 `[来源：章节"Y"]`
- 无法回答时明确说明，不编造

**输出**：`state["answer"]`

---

## 4. 运行脚本与操作步骤

### 4.1 脚本路径

```
/Users/tanglin/VibeCoding/GraphRagAgent/agentic_rag/
├── pipeline.py          ← 主入口（CLI）
├── graph.py             ← LangGraph 图定义
├── config.py            ← 环境配置加载
├── .env                 ← 实际配置（含 API Key，不提交 git）
├── .env.example         ← 配置模板
├── .venv/               ← 独立虚拟环境（Python 3.13）
└── CLAUDE.md            ← 运维操作手册
```

### 4.2 前置条件

在运行 Agentic RAG 前，必须确保以下两个上游 pipeline 已完成：

```bash
# 检查向量索引是否已建立
ls /Users/tanglin/VibeCoding/GraphRagAgent/rag_pipeline/chroma_db/
# 应有: chroma.sqlite3 + bm25_docs.pkl + {uuid}/

# 检查 KG JSONL 是否存在
ls /Users/tanglin/VibeCoding/GraphRagAgent/langextract_pipeline/output/
# 应有: kg_extraction_*.jsonl
```

### 4.3 环境配置

```bash
# 进入目录，激活虚拟环境
cd /Users/tanglin/VibeCoding/GraphRagAgent/agentic_rag
source .venv/bin/activate

# .env 最小配置（若已在 rag_pipeline/.env 中配置，可自动 fallback）
DASHSCOPE_API_KEY=sk-xxxx
LLM_MODEL_ID=qwen3.6-plus
LLM_PROVIDER=dashscope
```

### 4.4 完整操作步骤

#### Step 1：确认上游索引已就绪

```bash
# 如果 chroma_db 不存在，先运行 rag_pipeline 构建索引
cd /Users/tanglin/VibeCoding/GraphRagAgent/rag_pipeline
source .venv/bin/activate
python pipeline.py build "0.LangChain技术生态介绍"
```

#### Step 2：运行 Agentic RAG（单次查询）

```bash
cd /Users/tanglin/VibeCoding/GraphRagAgent/agentic_rag
source .venv/bin/activate
python pipeline.py "LangChain 的核心组件有哪些？"
```

#### Step 3：交互模式（多轮问答）

```bash
python pipeline.py
# 进入 REPL：输入问题后回车，输入 quit 退出
```

#### Step 4：验证图结构（开发调试）

```bash
python -c "
from graph import build_graph
from unittest.mock import MagicMock
from retrievers.kg_retriever import KGRetriever
app = build_graph(MagicMock(), MagicMock(spec=KGRetriever))
print(list(app.get_graph().nodes.keys()))
"
# 预期输出: ['__start__', 'route_question', 'retrieve', 'grade_documents', 'rewrite_question', 'generate_answer', '__end__']
```

### 4.5 依赖安装

```bash
cd agentic_rag
python -m venv .venv
source .venv/bin/activate
pip install langgraph langchain langchain-openai langchain-chroma \
            langchain-community langchain-classic rank-bm25 chromadb python-dotenv
```

---

## 5. 输入规范（AgentState）

Agentic RAG 的输入通过 `AgentState` TypedDict 传入，调用方需构造初始 state：

```python
from graph import get_default_graph

app = get_default_graph()
result = app.invoke({
    "question": "用户问题文本",       # str，必填
    "original_question": "用户问题",  # str，必填（与 question 相同，改写后保留原始）
    "route": "",                       # str，留空由 Node1 填充
    "kg_results": [],                  # list，留空由 Node2 填充
    "passage_results": [],             # list，留空由 Node2 填充
    "merged_context": "",              # str，留空由 Node2 填充
    "sufficient": False,               # bool，由 Node3 填充
    "rewrite_count": 0,                # int，累计改写次数
    "answer": "",                      # str，留空由 Node5 填充
})
```

---

## 6. 输出规范（前后端联调字段）

### 6.1 完整输出结构（app.invoke() 返回值）

```python
result: AgentState = {
    # ── 核心输出 ──────────────────────────────────────────────
    "answer": str,                    # 最终答案（Markdown 格式）

    # ── 路由与执行信息 ────────────────────────────────────────
    "route": str,                     # 实际执行的路由策略
    "original_question": str,         # 用户原始问题
    "question": str,                  # 最终使用的问题（可能经过改写）
    "rewrite_count": int,             # 实际改写次数（0~MAX_REWRITE_ATTEMPTS）
    "sufficient": bool,               # 最终检索充分性评估结果

    # ── 检索结果 ──────────────────────────────────────────────
    "kg_results": list[dict],         # KG 实体检索结果（详见 6.2）
    "passage_results": list[Document], # 段落检索结果（详见 6.3）
    "merged_context": str,            # 两路结果合并后的上下文文本
}
```

### 6.2 kg_results 字段规范

每个元素是一个字典，包含以下字段：

```python
{
    "entity_text": str,      # 实体名称，如 "LangChain"
    "entity_class": str,     # 实体类型，如 "product" / "concept" / "technology"
    "attributes": dict,      # 实体属性字典（key-value 结构）
                             # 示例：{"type": "大模型框架", "open_sourced": "2022年10月"}
    "document_id": str,      # 来源文档 ID，如 "0.LangChain技术生态介绍"
    "char_start": int,       # 实体在原文中的起始字符位置
    "char_end": int,         # 实体在原文中的结束字符位置
    "alignment_status": str, # 对齐状态："match_exact" / "match_fuzzy" / "not_grounded"
    "context_snippet": str,  # 实体在原文中±200字的上下文片段
}
```

**示例**：
```json
{
    "entity_text": "LangSmith",
    "entity_class": "product",
    "attributes": {
        "type": "开发平台",
        "function": "调试, 测试, 监控, 评估LLM应用"
    },
    "document_id": "0.LangChain技术生态介绍",
    "char_start": 1052,
    "char_end": 1061,
    "alignment_status": "match_exact",
    "context_snippet": "## 1. LangSmith\n\nLangSmith是一个帮助开发者调试..."
}
```

### 6.3 passage_results 字段规范

每个元素是 `langchain_core.documents.Document`，包含：

```python
doc.page_content: str        # chunk 文本内容（500~1000字）

doc.metadata: {
    "document_id": str,      # 文档 ID，如 "0.LangChain技术生态介绍"
    "section_title": str,    # 所属章节标题，如 "1. LangSmith"
    "section_level": int,    # 标题层级（1~6，0=无标题）
    "page_idx": int,         # 原始页码（0-based）
    "char_start": int,       # 在 full.md 中的字符起始偏移
    "char_end": int,         # 在 full.md 中的字符结束偏移
    "chunk_type": str,       # "text" 或 "table"
    "table_caption": str,    # 仅 table chunk 有此字段
    "entities": str,         # JSON 字符串，如 '["LangSmith", "LangChain"]'
    "entity_types": str,     # JSON 字符串，如 '["product", "product"]'
    "source": str,           # 原始目录绝对路径
}
```

> **注意**：`entities` 和 `entity_types` 存储为 JSON 字符串（Chroma 不支持空列表 metadata），前端读取时需 `json.loads(meta["entities"])`。

### 6.4 前端对接建议字段映射

面向前端展示，建议将 `result` 处理为以下结构：

```json
{
    "answer": "最终答案（Markdown 文本）",
    "meta": {
        "route": "hybrid_query",
        "rewrite_count": 0,
        "question_used": "（经改写后的问题，若未改写=原始问题）"
    },
    "sources": {
        "kg_entities": [
            {
                "name": "LangChain",
                "type": "product",
                "attributes": {"type": "大模型框架"},
                "context": "原文上下文片段",
                "document": "0.LangChain技术生态介绍"
            }
        ],
        "passages": [
            {
                "content": "chunk 文本",
                "section": "1. LangSmith",
                "page": 0,
                "document": "0.LangChain技术生态介绍",
                "entities": ["LangSmith"],
                "char_range": [1052, 1400]
            }
        ]
    }
}
```

### 6.5 answer 格式约定

- 格式：**Markdown**（支持 `##` 标题、`|` 表格、`**加粗**`、列表）
- 引用标注：行内引用，格式为 `[来源：实体 X]` 或 `[来源：章节"Y"]`
- 无法回答时：明确说明缺失信息，不编造，建议补充对应文档

---

## 7. 路由策略规范

### 7.1 路由分类规则

| 路由类型 | 触发条件 | 检索策略 | 典型问题 |
|---------|---------|---------|---------|
| `entity_query` | 问特定实体的属性/功能/参数 | 仅 KG 检索 | "LangSmith 是什么？" |
| `semantic_query` | 问概念/原理/流程/机制 | 仅段落检索 | "RAG 的工作原理是什么？" |
| `hybrid_query` | 比较/综合/多实体/架构问题 | KG + 段落并行 | "LangChain 和 LlamaIndex 的区别？" |
| `direct_answer` | 通用知识/闲聊/无需文档 | 不检索 | "你好" / "Python 语法问题" |

### 7.2 实测路由准确率（3 问题验证）

| 问题 | 预期路由 | 实际路由 | 是否正确 |
|------|---------|---------|---------|
| "LangChain 核心组件有哪些？它与 LlamaIndex 有什么区别？" | `hybrid_query` | `hybrid_query` | ✅ |
| "LangSmith 是什么？它在 LangChain 生态中承担什么角色？" | `entity_query` | `entity_query` | ✅ |
| "LangGraph 适合构建哪类应用？与普通 Chain 有什么本质区别？" | `hybrid_query` | `hybrid_query` | ✅ |

---

## 8. 检索结果规范

### 8.1 KGRetriever 实现细节

```
数据源：langextract_pipeline/output/kg_extraction_*.jsonl
过滤条件：alignment_status == "match_exact"（仅精确对齐的实体）
索引方式：BM25（rank-bm25），索引字段 = entity_text + 所有 attribute values
上下文窗口：原文±200字（KG_CONTEXT_WINDOW=200）
返回数量：top_k=5（KG_TOP_K）

实测数据：
  - JSONL 文件：3 个
  - 总实体数：130 个
  - BM25 索引字段：entity_text + attribute value 拼接
```

### 8.2 HybridRetriever 实现细节

```
数据源：rag_pipeline/chroma_db/（Chroma 向量库 + bm25_docs.pkl）
向量检索：Chroma HNSW，embedding=text-embedding-v4（1024维），权重 0.6
关键词检索：BM25Retriever（rank-bm25），权重 0.4
融合算法：Reciprocal Rank Fusion（RRF，k=60）
返回数量：每路 top_k=5，RRF 去重后实际最多 9 条

实测数据：
  - Chroma chunks：15 个
  - BM25 docs：15 个
  - 实际召回（RRF 去重后）：9 个
```

### 8.3 merged_context 格式

```
=== 知识图谱实体 ===
[实体 1] LangChain (product)
  属性: type=元老级Agent开发工具, 大模型开发框架 | open_sourced=2022年10月开源
  原文: # LangChain快速入门与Agent开发实战...

[实体 2] LlamaIndex (product)
  属性: type=大模型开发框架 | focus=文档处理, RAG
  原文: # 三、LangChain生态竞品分析...

=== 文档段落 ===
[1] 文档：0.LangChain技术生态介绍  章节：4. 组件（Component）
    相关实体：LangChain Expression Language, LCEL
在LangChain中，Components是一系列可组合的构建块...

[2] 文档：0.LangChain技术生态介绍  章节：1. LlamaIndex
...
```

---

## 9. 关键参数规范

### 9.1 agentic_rag/.env 配置项

| 参数 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `DASHSCOPE_API_KEY` | 是 | — | DashScope API Key |
| `LLM_PROVIDER` | 否 | `dashscope` | `dashscope` \| `deepseek` |
| `LLM_MODEL_ID` | 否 | `qwen-plus` | LLM 模型名（实测 `qwen3.6-plus`） |
| `DASHSCOPE_BASE_URL` | 否 | `https://dashscope.aliyuncs.com/compatible-mode/v1` | DashScope 接口地址 |
| `DASHSCOPE_EMBEDDING_MODEL` | 否 | `text-embedding-v3` | Embedding 模型（实测 `text-embedding-v4`） |
| `DEEPSEEK_API_KEY` | 是* | — | DeepSeek API Key |
| `RETRIEVAL_TOP_K` | 否 | `5` | 段落检索 top-k |
| `VECTOR_WEIGHT` | 否 | `0.6` | 向量检索权重 |
| `BM25_WEIGHT` | 否 | `0.4` | BM25 权重 |
| `KG_TOP_K` | 否 | `5` | KG 实体检索 top-k |
| `KG_CONTEXT_WINDOW` | 否 | `200` | 实体原文上下文窗口（字符数） |
| `MAX_REWRITE_ATTEMPTS` | 否 | `2` | 最大问题改写次数 |
| `CHROMA_PERSIST_DIR` | 否 | `../rag_pipeline/chroma_db` | 向量库路径 |
| `LANGEXTRACT_OUTPUT_DIR` | 否 | `../langextract_pipeline/output` | KG JSONL 路径 |

> *当 `LLM_PROVIDER=deepseek` 时必填

### 9.2 config.py 关键设计：sys.path 注入与字段兼容

```python
# agentic_rag/config.py 在导入时执行以下逻辑：
_rag_path = str(RAG_PIPELINE_DIR.resolve())
if _rag_path not in sys.path:
    sys.path.insert(0, _rag_path)

# 必须包含 rag_pipeline 需要的字段（防止 import config 名称冲突时报错）
VECTOR_WEIGHT: float = float(os.getenv("VECTOR_WEIGHT", "0.6"))
BM25_WEIGHT: float = float(os.getenv("BM25_WEIGHT", "0.4"))
# 以及 RETRIEVAL_TOP_K、CHROMA_PERSIST_DIR、DASHSCOPE_* 等
```

---

## 10. MVP 实测结果（3 问题）

### 测试配置

| 项目 | 值 |
|------|-----|
| LLM | `qwen3.6-plus`（DashScope） |
| Embedding | `text-embedding-v4`（1024维） |
| KG 实体数 | 130 个（来自 3 个 JSONL 文件） |
| 向量 chunks 数 | 15 个（`0.LangChain技术生态介绍`） |
| 段落检索 top_k | 5（RRF 后实际召回 9） |
| KG 检索 top_k | 5 |

---

### 问题 1：LangChain 的核心组件有哪些？它与 LlamaIndex 有什么区别？

**路由**：`hybrid_query` | KG 5实体 + 段落 9块 | 充分 ✅ | 改写 0次

**KG 命中实体**：

| 排名 | 实体 | 类型 | 关键属性 |
|------|------|------|---------|
| 1 | LangChain | product | type=大模型开发框架, core_components=链+代理 |
| 2 | LlamaIndex | product | focus=文档处理+RAG, open_sourced=2022年11月 |
| 3 | LangChain Expression Language | concept | abbreviation=LCEL, 原生支持流式/异步/批处理 |
| 4 | LangSmith | product | function=调试+测试+监控+评估 |
| 5 | LangGraph | product | type=有状态多角色应用框架 |

**段落命中（前3）**：

| 排名 | 章节 | 页码 | 类型 | 标注实体 |
|------|------|------|------|---------|
| 1 | 4. 组件（Component） | 0 | text | LCEL |
| 2 | 1. LlamaIndex | 0 | text | LlamaIndex |
| 3 | 1. LangSmith | 0 | text | LangSmith |

**最终答案质量**：

> LangChain 核心组件包括**链（Chain）**、**代理（Agent）**以及 **LCEL**（新一代链式调用语法，原生支持流式/异步/批处理）；Components 是模块化构建块，可组合构建复杂 AI 应用。
>
> LangChain vs LlamaIndex：LangChain 是通用大模型开发框架（2022-10），LlamaIndex 专注文档处理和 RAG（2022-11），在图索引结构和数据连接器方面更深入，是 RAG 场景首选。

**质量评价**：✅ 优秀——包含对比表格，来源标注精确，KG 实体属性与段落内容互补。

---

### 问题 2：LangSmith 是什么？它在 LangChain 生态中承担什么角色？

**路由**：`entity_query`（路由器准确识别为实体查询）| KG 5实体 | 充分 ✅ | 改写 0次

**KG 命中实体**：

| 排名 | 实体 | 类型 | 关键属性 |
|------|------|------|---------|
| 1 | LangSmith | product | type=开发平台, function=调试+测试+监控+评估 |
| 2 | LangSmith 追踪功能 | concept | 追踪LLM调用+Agent操作+工具调用的输入输出和延迟 |
| 3 | LangSmith评测 | concept | 创建+管理评估数据集，进行评测 |
| 4 | LangChain | product | 主体框架 |
| 5 | LangServe | product | 已被 LangGraph Platform 取代 |

**最终答案质量**：

> LangSmith 是 LangChain 生态中的综合性开发平台，核心能力：① 追踪调试；② 数据集评测；③ 在线监控；④ Prompt 管理。在生态中承担**可观测性与质量保障**角色，与 LangGraph（Agent 工作流）、LangGraph Platform（API 部署）共同构成开发闭环。

**质量评价**：✅ 优秀——KG 细粒度实体（追踪功能、评测）完整覆盖 4 项核心能力，生态角色定位准确。

**注**：`entity_query` 路由跳过了段落检索。LangSmith 的段落内容（详细核心能力列表）也在 chunks 中存在，若改为 `hybrid_query` 可获得更丰富上下文，但 KG 实体属性已覆盖核心信息。

---

### 问题 3：LangGraph 适合构建哪类应用？与普通 Chain 有什么本质区别？

**路由**：`hybrid_query` | KG 5实体 + 段落 9块 | 充分 ✅ | 改写 0次

**KG 命中实体**：

| 排名 | 实体 | 类型 | 关键属性 |
|------|------|------|---------|
| 1 | LangGraph | product | type=有状态多角色应用框架, 适用于循环工作流Agent |
| 2 | LangChain | product | type=大模型开发框架 |
| 3 | LangChain Expression Language | concept | LCEL，新一代链式调用语法 |
| 4 | LangGraph Platform | product | type=部署平台，取代 LangServe |
| 5 | LangSmith | product | 可观测性工具 |

**段落命中（前3）**：

| 排名 | 章节 | 页码 | 命中原因 |
|------|------|------|---------|
| 1 | 2. LangGraph | 0 | 直接定义："有状态、多角色应用框架，将步骤建模为图中的节点和边" |
| 2 | 4. 组件（Component） | 0 | LCEL 对比参照 |
| 3 | 1. LangSmith | 0 | 生态背景 |

**最终答案质量**：

> LangGraph 适合：循环工作流 Agent、多角色协作、有状态应用、复杂多步骤任务。
>
> 与普通 Chain 的本质区别：Chain（LCEL）是线性 DAG 执行，LangGraph 通过节点+边建图，支持循环、条件分支和跨步骤状态持久化，是复杂 Agent 系统的底层框架。

**质量评价**：✅ 优秀——"2. LangGraph"章节排在首位，对比表格维度完整（执行模式/状态管理/流程控制），本质区别（DAG vs 图+循环）描述准确。

---

### 综合质量评估

| 维度 | 结果 | 说明 |
|------|------|------|
| 路由准确率 | 3/3 (100%) | 所有问题路由正确 |
| KG 实体召回 | 所有问题命中核心实体 | 细粒度实体（追踪功能、评测）也被命中 |
| 段落检索相关性 | 目标章节均排前3 | RRF 融合效果良好 |
| 充分性评估 | 3/3 首次通过 | 无需问题改写 |
| 改写机制 | 未触发（0次改写） | 设计验证：充分时正确跳过 |
| 答案结构 | 3/3 含对比表格+来源引用 | Markdown 格式，结构清晰 |

---

## 11. 依赖版本清单

**Python 版本**：3.13  
**虚拟环境位置**：`agentic_rag/.venv/`

| 包名 | 用途 |
|------|------|
| `langgraph` | 5 节点 StateGraph 图框架 |
| `langchain` | 核心 LLM/Chain 接口 |
| `langchain-openai` | ChatOpenAI（DashScope / DeepSeek 兼容） |
| `langchain-chroma` | Chroma 向量库集成（来自 rag_pipeline 复用） |
| `langchain-community` | BM25Retriever（来自 rag_pipeline 复用） |
| `langchain-classic` | EnsembleRetriever（LangChain 1.x 拆分到此包） |
| `rank-bm25` | BM25 算法（KGRetriever + HybridRetriever） |
| `chromadb` | 向量库（来自 rag_pipeline 复用） |
| `python-dotenv` | .env 加载 |

---

## 12. 与上游 Pipeline 的对接关系

### 12.1 三层 Pipeline 关系图

```
┌──────────────────────────────────────────────────────────────────┐
│  阶段一：文档解析（mineru_parser）                                 │
│  mineru_parser/output/{文档名}/                                   │
│    ├── full.md                ← 主文本                            │
│    └── *_content_list.json   ← 结构化块                           │
└─────────────────────────┬────────────────────────────────────────┘
                          │
          ┌───────────────┴───────────────┐
          ▼                               ▼
┌─────────────────────┐         ┌──────────────────────────┐
│  阶段二A：向量索引   │         │  阶段二B：KG 抽取         │
│  (rag_pipeline)     │         │  (langextract_pipeline)  │
│  chroma_db/         │         │  output/*.jsonl          │
│  bm25_docs.pkl      │         │  130 个实体（3 文档）     │
└──────────┬──────────┘         └────────────┬─────────────┘
           │                                  │
           └──────────────┬───────────────────┘
                          ▼
┌──────────────────────────────────────────────────────────────────┐
│  阶段三：Agentic RAG 查询（agentic_rag）                          │
│  双路检索（KG + 向量段落）→ LangGraph 5 节点图 → 最终答案          │
└──────────────────────────────────────────────────────────────────┘
```

### 12.2 数据目录依赖

| 依赖 | 路径 | 来源 |
|------|------|------|
| Chroma 向量库 | `rag_pipeline/chroma_db/` | rag_pipeline build |
| BM25 语料缓存 | `rag_pipeline/chroma_db/bm25_docs.pkl` | rag_pipeline build |
| KG JSONL | `langextract_pipeline/output/kg_extraction_*.jsonl` | LangExtract pipeline |

### 12.3 上游 Pipeline 对接接口

**rag_pipeline 接口**（通过 sys.path 注入直接调用）：
```python
from retriever import create_hybrid_retriever
retriever = create_hybrid_retriever(top_k=5)
docs = retriever.invoke(query)   # list[Document]
```

**langextract_pipeline 接口**（直接读取 JSONL）：
```python
# kg_retriever.py 实现：
for jsonl_file in Path(jsonl_dir).glob("*.jsonl"):
    with open(jsonl_file) as f:
        for line in f:
            record = json.loads(line)
            for ext in record.get("extractions", []):
                if ext["alignment_status"] == "match_exact":
                    # 加入 BM25 索引
```
