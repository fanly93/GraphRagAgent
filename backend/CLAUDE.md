# GraphRAG Agent — 后端服务手册

## 项目路径

```
GraphRagAgent/
└── backend/          ← 后端根目录（所有命令均在此目录下执行）
```

---

## 首次初始化

```bash
cd /Users/tanglin/VibeCoding/GraphRagAgent/backend

# 1. 创建虚拟环境
python -m venv .venv

# 2. 激活虚拟环境
source .venv/bin/activate        # macOS / Linux
# .venv\Scripts\activate         # Windows

# 3. 安装依赖
pip install -r requirements.txt

# 4. 配置环境变量（复制模板后填写真实密钥）
cp .env.example .env
```

---

## 启动服务

```bash
cd /Users/tanglin/VibeCoding/GraphRagAgent/backend
source .venv/bin/activate

# 开发模式（热重载）
uvicorn main:app --reload --port 8000

# 生产模式
uvicorn main:app --host 0.0.0.0 --port 8000
```

服务启动后：
- API 根路径：`http://localhost:8000`
- OpenAPI 交互文档：`http://localhost:8000/docs`
- 健康检查：`http://localhost:8000/api/v1/health`

---

## 环境变量（backend/.env）

| 变量 | 说明 | 必填 |
|------|------|------|
| `MINERU_API_TOKEN` | MinerU 云端解析 API Token | ✓ |
| `MINERU_BASE_URL` | MinerU 服务地址，默认 `https://mineru.net` | |
| `LLM_PROVIDER` | `dashscope`（阿里云）或 `deepseek` | ✓ |
| `LLM_MODEL_ID` | 模型 ID，如 `qwen3.6-plus` | ✓ |
| `DASHSCOPE_API_KEY` | 阿里云灵积 API Key | ✓ |
| `DASHSCOPE_BASE_URL` | 默认 `https://dashscope.aliyuncs.com/compatible-mode/v1` | |
| `DASHSCOPE_EMBEDDING_MODEL` | 默认 `text-embedding-v4` | |
| `DEEPSEEK_API_KEY` | DeepSeek API Key（provider=deepseek 时必填）| |
| `PORT` | 服务端口，默认 `8000` | |
| `QA_TIMEOUT_SEC` | 问答超时秒数，默认 `120` | |
| `MAX_UPLOAD_SIZE_MB` | 最大上传文件大小，默认 `200` | |

---

## 目录结构

```
backend/
├── main.py                    # FastAPI 应用入口，lifespan、中间件、路由注册
├── config.py                  # 从 .env 加载所有配置
├── models.py                  # Pydantic 请求/响应模型
├── database.py                # SQLite (aiosqlite) CRUD
├── requirements.txt
├── .env                       # 真实密钥（不提交 git）
├── .env.example               # 配置模板
│
├── routers/                   # HTTP 路由层
│   ├── documents.py           # 上传 / 状态 / 列表 / 删除
│   ├── qa.py                  # 问答接口
│   └── health.py              # 健康检查
│
├── services/                  # 业务逻辑层
│   ├── mineru_service.py      # MinerU Precision/Agent API 封装 + 轮询
│   ├── index_service.py       # 并行向量索引 + KG 索引构建
│   └── qa_service.py          # LangGraph 问答调用 + 响应格式化
│
├── core/                      # 核心算法层
│   ├── embeddings.py          # DashScope Embedding（check_embedding_ctx_length=False）
│   ├── structure_splitter.py  # 文档结构感知切分（content_list.json 优先）
│   ├── indexer.py             # Chroma 向量索引 + BM25 Pickle
│   ├── kg_extractor.py        # LLM 实体抽取 → JSONL
│   ├── kg_retriever.py        # KG BM25 检索
│   ├── hybrid_retriever.py    # 向量 + BM25 混合检索（EnsembleRetriever）
│   ├── rag_graph.py           # LangGraph 5 节点 Agentic RAG 图
│   └── prompts.py             # 所有 Prompt 模板
│
├── data/jobs.db               # SQLite 数据库（首次启动自动创建）
├── uploads/                   # 上传文件存储（按 doc_id 命名）
├── output/                    # MinerU 解析输出（{doc_id}/ 子目录）
├── chroma_db/                 # Chroma 向量索引持久化目录
└── kg_output/                 # KG 实体 JSONL 文件（{doc_id}.jsonl）
```

---

## 文档处理状态机

```
UPLOADED → PARSING → PARSED → INDEXING → READY
                ↘ PARSE_FAILED      ↘ INDEX_FAILED
```

| 状态 | 含义 |
|------|------|
| `UPLOADED` | 文件已保存，MinerU 任务提交中 |
| `PARSING` | MinerU 云端解析进行中（轮询 10s/次，最长 600s）|
| `PARSED` | 解析完成，自动触发索引构建 |
| `INDEXING` | 向量索引 + KG 索引并行构建中 |
| `READY` | 全部就绪，可以问答 |
| `PARSE_FAILED` | MinerU 解析失败（含错误原因）|
| `INDEX_FAILED` | 索引构建失败（含错误原因）|

---

## API 接口一览

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/health` | 服务健康检查 |
| POST | `/api/v1/documents/upload` | 上传文件，触发异步解析 |
| GET | `/api/v1/documents` | 文档列表（支持 status 过滤、分页）|
| GET | `/api/v1/documents/{doc_id}/status` | 查询单个文档状态 |
| DELETE | `/api/v1/documents/{doc_id}` | 删除文档及全部索引数据 |
| POST | `/api/v1/qa/query` | 问答查询 |

---

## 关键实现说明

1. **qwen3 系列模型**：必须传 `extra_body={"enable_thinking": False}`，否则每次 LLM 调用约 50-70s，开启后约 3-5s。已在 `core/rag_graph.py` 和 `services/index_service.py` 中处理。

2. **DashScope Embedding**：必须设置 `check_embedding_ctx_length=False, chunk_size=10`，否则 400 报错。见 `core/embeddings.py`。

3. **MinerU 上传**：PUT 请求上传文件时不能带 `Content-Type` Header，必须带 `Content-Length`。见 `services/mineru_service.py`。

4. **索引更新后**：`index_service.build_both()` 完成后自动调用 `reset_graph()`，下次问答请求时重新加载新索引。

5. **并发安全**：LangGraph `invoke` 是同步阻塞调用，通过 `loop.run_in_executor(None, ...)` 在线程池中执行，不阻塞 asyncio 事件循环。
