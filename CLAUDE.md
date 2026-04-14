# GraphRAG Agent — 项目规范

## 目录结构

```
GraphRagAgent/
├── frontend/     # 前端：Vite + React 源码与构建配置；依赖锁定见 package-lock.json（node_modules 不提交）
├── backend/      # 后端：所有 FastAPI 代码、.venv 虚拟环境、SQLite 数据库、上传文件
├── docs/         # 规范文档
└── CLAUDE.md
```

**强制约定**：
- 前端所有文件（代码、配置、环境）必须放在 `frontend/` 下
- 后端所有文件（代码、配置、数据库、上传文件、虚拟环境）必须放在 `backend/` 下

---

## 环境变量管理

- 后端所有外部服务配置（API Key、模型 ID、路径等）统一写在 `backend/.env`
- `.env` 文件**禁止提交 git**，已在 `.gitignore` 中忽略
- 提交 `backend/.env.example` 作为配置模板（不含真实密钥）

---

## 后端虚拟环境

后端必须使用独立的 Python 虚拟环境，不得使用全局环境：

```bash
cd backend
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

启动服务：

```bash
cd backend
source .venv/bin/activate
uvicorn main:app --reload --port 8000
```

---

## 前端（Vite + React）

依赖与版本锁定以 **`frontend/package-lock.json`** 为准，CI/新环境建议：

```bash
cd frontend
npm ci        # 严格按 lockfile 安装（推荐）
npm run dev   # 开发：默认 http://localhost:5173/
npm run build # 产物：frontend/dist/
```

详见 `frontend/CLAUDE.md`。
