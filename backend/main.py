"""GraphRAG Agent 后端服务入口。"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import sys
sys.path.insert(0, str(Path(__file__).parent))
import config
from database import init_db
from routers import documents, qa, health


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时初始化数据库
    await init_db()
    print("=" * 50)
    print("GraphRAG Agent Backend 启动")
    print(f"  DB:          {config.DB_PATH}")
    print(f"  Uploads:     {config.UPLOAD_DIR}")
    print(f"  MinerU Out:  {config.MINERU_OUTPUT_DIR}")
    print(f"  Chroma DB:   {config.CHROMA_PERSIST_DIR}")
    print(f"  KG Output:   {config.KG_OUTPUT_DIR}")
    print(f"  LLM:         {config.LLM_PROVIDER} / {config.LLM_MODEL_ID}")
    print("=" * 50)
    yield
    print("服务关闭")


app = FastAPI(
    title="GraphRAG Agent API",
    description="多模态 RAG 问答后端服务",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS（前端开发时跨域）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 全局请求 ID 中间件
@app.middleware("http")
async def add_request_id(request: Request, call_next):
    request_id = str(uuid.uuid4())
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


# 全局 422 校验错误处理（统一错误格式）
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = exc.errors()
    first = errors[0] if errors else {}
    field = ".".join(str(x) for x in first.get("loc", [])[1:]) or "unknown"
    msg = first.get("msg", "输入参数校验失败")
    return JSONResponse(
        status_code=400,
        content={"error": "INVALID_REQUEST", "message": f"{field}: {msg}"},
    )


# 全局异常处理（将 dict detail 透传为 JSON 错误体）
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"error": "INTERNAL_ERROR", "message": str(exc)},
    )


# 注册路由
API_PREFIX = "/api/v1"
app.include_router(documents.router, prefix=API_PREFIX)
app.include_router(qa.router, prefix=API_PREFIX)
app.include_router(health.router, prefix=API_PREFIX)


@app.get("/")
async def root():
    return {"service": "GraphRAG Agent API", "version": "1.0.0", "docs": "/docs"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=config.PORT, reload=config.DEBUG)
