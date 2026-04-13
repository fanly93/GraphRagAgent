# GraphRAG Agent — 后端运维手册

## 快速启动

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env    # 填写 MINERU_API_TOKEN、DASHSCOPE_API_KEY
uvicorn main:app --reload --port 8000
```

API 文档：http://localhost:8000/docs

## 目录说明

```
backend/
├── main.py              # FastAPI 入口
├── config.py            # 配置（读 .env）
├── models.py            # Pydantic 模型
├── database.py          # SQLite CRUD
├── routers/             # HTTP 路由层
│   ├── documents.py     # 上传/状态/列表/删除
│   ├── qa.py            # 问答
│   └── health.py        # 健康检查
├── services/            # 业务逻辑层
│   ├── mineru_service.py   # MinerU API 封装
│   ├── index_service.py    # 并行索引构建
│   └── qa_service.py       # 问答服务
├── core/                # 核心算法层
│   ├── structure_splitter.py  # 文档结构感知切分
│   ├── indexer.py             # Chroma + BM25 索引
│   ├── kg_extractor.py        # KG 实体抽取
│   ├── kg_retriever.py        # KG BM25 检索
│   ├── hybrid_retriever.py    # 混合检索
│   ├── rag_graph.py           # LangGraph 5 节点图
│   ├── embeddings.py          # Embedding 模型
│   └── prompts.py             # 所有 Prompt 模板
├── data/jobs.db         # SQLite（自动创建）
├── uploads/             # 上传文件临时存储
├── output/              # MinerU 解析结果（doc_id 子目录）
├── chroma_db/           # 向量索引
└── kg_output/           # KG JSONL 文件
```

## 文档状态机

```
UPLOADED → PARSING → PARSED → INDEXING → READY
                 ↘ PARSE_FAILED     ↘ INDEX_FAILED
```

## 关键注意事项

1. **MinerU PUT 上传**：不能加 Content-Type，必须加 Content-Length
2. **索引更新后**：`reset_graph()` 会重置 RAG 图单例，下次问答自动加载新索引
3. **并发安全**：LangGraph invoke 是同步调用，通过 `run_in_executor` 在线程池执行
4. **KG 依赖 LLM**：每次 build_kg_index 会调用 LLM 抽取实体，注意 token 费用
