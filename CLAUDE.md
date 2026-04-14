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

## 后端启动（FastAPI + uvicorn）

后端必须使用独立的 Python 虚拟环境，不得使用全局环境。

**首次初始化**：

```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env             # 然后填写真实密钥
```

**启动服务**：

```bash
cd backend
source .venv/bin/activate
uvicorn main:app --reload --port 8000
```

服务地址：`http://localhost:8000` | API 文档：`http://localhost:8000/docs`

**停止服务**：

```bash
# 前台运行时直接 Ctrl+C
# 后台运行时：
pkill -f "uvicorn main:app"
```

---

## 前端启动（Vite + React）

> 前端通过 Vite 代理将 `/api` 请求转发到后端（`http://localhost:8000`），
> 因此**使用前端前必须先启动后端服务**。

**首次初始化**：

```bash
cd frontend
npm install   # 首次安装或依赖变更后执行
```

**启动开发服务**：

```bash
cd frontend
npm run dev   # 开发：http://localhost:5173/
```

**构建产物**：

```bash
cd frontend
npm run build   # 产物输出到 frontend/dist/
```

**停止服务**：

```bash
# 前台运行时直接 Ctrl+C
# 后台运行时：
pkill -f "vite"
```

详见 `frontend/CLAUDE.md`。
