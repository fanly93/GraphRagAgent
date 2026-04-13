# RAG Pipeline — 操作指南

> 完整规范文档：`../docs/mineru-rag_pipeline-spec-v1.0.md`

## 架构概述

```
MinerU content_list.json + full.md
        │
        ▼
structure_splitter.py   ← 结构感知切分（标题边界 + 短文本合并 + 顺序游标定位 + 表格独立 chunk）
        │ list[Document]（带 metadata：section_title/page_idx/chunk_type/entities）
        ▼
indexer.py
  ├── Chroma（chroma_db/）     向量持久化，1024维（text-embedding-v4）
  └── bm25_docs.pkl            BM25 语料缓存
        │
        ▼
retriever.py
  EnsembleRetriever（向量 0.6 + BM25 0.4，RRF 融合）
        │ list[Document]
        ▼
pipeline.py / llm_provider.py  ← LLM 生成答案（含来源引用）
```

## 环境准备

```bash
cd /Users/tanglin/VibeCoding/GraphRagAgent/rag_pipeline

# 激活专属虚拟环境（勿与 langextract_pipeline 混用）
source .venv/bin/activate

# 首次配置
cp .env.example .env
# 编辑 .env，至少填写：
#   DASHSCOPE_API_KEY=sk-xxx
#   DASHSCOPE_EMBEDDING_MODEL=text-embedding-v4
#   LLM_MODEL_ID=qwen3.6-plus
```

## 快速开始

```bash
source .venv/bin/activate

# 构建索引（推荐：指定文档，避免索引无效文档）
python pipeline.py build "0.LangChain技术生态介绍"

# 强制重建（清空旧索引）
python pipeline.py build "0.LangChain技术生态介绍" --force

# 查询
python pipeline.py query "LangChain是什么？"

# 查看索引统计
python pipeline.py stats
```

## 输入文件说明

**只需要两类文件：**

| 文件 | 必要性 | 用途 |
|------|--------|------|
| `*_content_list.json` | 必须 | 结构化块（type/text/text_level/table_body），切分主数据源 |
| `full.md` | 辅助 | 无 content_list 时降级使用；char_start 字符定位 |

**不需要：** `layout.json` / `*_origin.pdf` / `images/`

## 配置参数（.env）

| 变量 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `DASHSCOPE_API_KEY` | 是 | — | DashScope API Key |
| `DASHSCOPE_BASE_URL` | 否 | `https://dashscope.aliyuncs.com/compatible-mode/v1` | 接口地址 |
| `DASHSCOPE_EMBEDDING_MODEL` | 否 | `text-embedding-v3` | Embedding 模型（实测用 v4） |
| `LLM_PROVIDER` | 否 | `dashscope` | `dashscope` \| `deepseek` |
| `LLM_MODEL_ID` | 否 | `qwen-plus` | LLM 模型名 |
| `CHUNK_SIZE` | 否 | `500` | chunk 目标字符数（推荐 800） |
| `CHUNK_OVERLAP` | 否 | `80` | 重叠字符数（推荐 100） |
| `VECTOR_WEIGHT` | 否 | `0.6` | 向量检索权重 |
| `BM25_WEIGHT` | 否 | `0.4` | BM25 关键词权重 |
| `RETRIEVAL_TOP_K` | 否 | `4` | 每路检索 top-k（推荐 5） |
| `MINERU_OUTPUT_DIR` | 否 | `../mineru_parser/output` | MinerU 解析结果目录 |

## 实测结果（0.LangChain技术生态介绍）

- 切分：**15 chunks**（text: 13，table: 2）
- 向量维度：**1024**（DashScope text-embedding-v4）
- 索引大小：**912 KB**
- Chroma collection：`graphrag_docs`
- char_start 单调递增：13/13 文本 chunk 全部通过
- 实体覆盖：11/15 chunk 有 LangExtract 实体注入
- 检索：top_k=5，实际召回 9 条（RRF 融合后去重）
- 问答效果：3/3 问题命中对应章节，回答含章节引用

## 已知问题与修复记录

| 问题 | 修复位置 | 修复方式 |
|------|---------|---------|
| DashScope 不支持 tokenized 批量输入 | `embeddings.py` | `check_embedding_ctx_length=False` |
| DashScope 单批最多 10 条文本 | `embeddings.py` | `chunk_size=10` |
| Chroma 不允许空列表 metadata | `structure_splitter.py` | `entities`/`entity_types` 序列化为 JSON 字符串 |
| EnsembleRetriever 包路径变化（LangChain 1.x） | `retriever.py` | 从 `langchain_classic.retrievers` 导入 |
| 短文本（<MIN_CHUNK_SIZE）被静默丢弃 | `structure_splitter.py` | `_append_to_last()` 追加到前一个 Document |
| char_start 定位偏差（重复文本被定位到首次出现处） | `structure_splitter.py` | 顺序游标 `_sequential_find(text, needle, cursor)` |
| 短章节产生孤立碎片 chunk | `structure_splitter.py` | 复用 `_append_to_last()` 合并到前一个 chunk |

## Agentic RAG 对接接口

```python
from retriever import create_hybrid_retriever
from llm_provider import create_llm

retriever = create_hybrid_retriever()
docs = retriever.invoke(query)   # 返回 list[Document]

# metadata 关键字段
doc.metadata["document_id"]    # 文档ID
doc.metadata["section_title"]  # 章节标题
doc.metadata["chunk_type"]     # text | table
doc.metadata["entities"]       # JSON字符串，需 json.loads() 解析
```

## 目录结构

```
rag_pipeline/
├── .env                  ← 环境配置（含 API Key，不提交 git）
├── .env.example          ← 配置模板
├── .venv/                ← 独立虚拟环境（Python 3.13）
├── chroma_db/            ← 索引持久化（不提交 git）
│   ├── {uuid}/           ← HNSW 向量索引
│   ├── bm25_docs.pkl     ← BM25 语料缓存
│   └── chroma.sqlite3    ← 元数据
├── requirements.txt      ← 依赖锁定
├── config.py             ← 配置加载
├── structure_splitter.py ← 结构感知切分（核心）
├── embeddings.py         ← Embedding 工厂
├── indexer.py            ← 索引构建与加载
├── retriever.py          ← Hybrid 检索器
├── llm_provider.py       ← LLM 工厂
└── pipeline.py           ← CLI 入口
```

## 后续扩展（LlamaIndex）

扩展点已预留，替换时保持相同接口：

- `embeddings.py`：添加 LlamaIndex embedding 工厂
- `indexer.py`：添加 `LlamaIndexIndexer` 类（相同 build/load 接口）
- `retriever.py`：替换为 `LlamaIndex QueryFusionRetriever`（保持 `.invoke()` 接口）
