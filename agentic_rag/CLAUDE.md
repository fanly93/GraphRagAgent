# Agentic RAG — 操作指南

## 项目概述

基于 LangGraph 的 5 节点 Agentic RAG 系统，融合向量+BM25 混合检索（来自 `rag_pipeline`）和知识图谱检索（来自 `langextract_pipeline`）。

## 目录结构

```
agentic_rag/
├── config.py              # 环境变量加载，注入 rag_pipeline 到 sys.path
├── state.py               # AgentState TypedDict（9 个字段）
├── prompts.py             # 5 个 Prompt 模板
├── graph.py               # LangGraph StateGraph 图构建与编译
├── pipeline.py            # CLI 入口（交互 / 单次查询）
├── nodes/
│   ├── router.py          # Node 1: route_question（4 路由分类）
│   ├── retriever.py       # Node 2: retrieve（KG / 段落 / 融合 / 直接）
│   ├── grader.py          # Node 3: grade_documents（JSON 充分性评估）
│   ├── rewriter.py        # Node 4: rewrite_question + should_rewrite 条件边
│   └── generator.py       # Node 5: generate_answer（带 KG + 段落引用）
└── retrievers/
    ├── kg_retriever.py    # KGRetriever: BM25 over LangExtract JSONL
    └── hybrid_retriever.py # 调用 rag_pipeline EnsembleRetriever
```

## 图执行流程

```
route_question → retrieve → grade_documents ──充分──→ generate_answer → END
                                    │
                                  不足
                                    ↓
                           rewrite_question → retrieve（循环，最多 MAX_REWRITE_ATTEMPTS 次）
```

## 快速启动

```bash
cd agentic_rag
source .venv/bin/activate

# 交互模式
python pipeline.py

# 单次提问
python pipeline.py "LangChain 支持哪些向量数据库？"
```

## 前置条件

1. `rag_pipeline/chroma_db/` 已建好索引（运行过 `rag_pipeline/pipeline.py build`）
2. `langextract_pipeline/output/` 有 LangExtract JSONL 产物
3. `.env` 已配置 `DASHSCOPE_API_KEY`（或复制 `.env.example`）

## 依赖安装

```bash
python -m venv .venv
source .venv/bin/activate
pip install langgraph langchain langchain-openai langchain-chroma \
            langchain-community langchain-classic rank-bm25 chromadb python-dotenv
```

## 路由策略

| 路由 | 触发场景 | 检索策略 |
|------|----------|----------|
| `entity_query` | 具体实体属性查询 | 仅 KG 检索 |
| `semantic_query` | 语义/概念查询 | 仅段落检索 |
| `hybrid_query` | 复杂多方面查询 | KG + 段落并行 |
| `direct_answer` | 通用知识/闲聊 | 不检索，直接回答 |

## 已知问题与注意事项

| 问题 | 解决方案 |
|------|----------|
| DashScope 不支持 `check_embedding_ctx_length` | `embeddings.py` 已设 `check_embedding_ctx_length=False, chunk_size=10` |
| Chroma 禁止空列表元数据 | entities/entity_types 序列化为 JSON 字符串 |
| LangChain 1.x EnsembleRetriever 迁移 | 从 `langchain_classic.retrievers` 导入 |
| LangExtract JSONL 无文档时 KG 检索返回空列表 | 正常降级，不影响段落检索路径 |
