"""Agentic RAG 配置加载。

复用 rag_pipeline 的 .env，同时支持自身 .env 覆盖。
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent
RAG_PIPELINE_DIR = BASE_DIR / "../rag_pipeline"

# 优先加载自身 .env，fallback 到 rag_pipeline/.env
_own_env = BASE_DIR / ".env"
_rag_env = RAG_PIPELINE_DIR / ".env"
if _own_env.exists():
    load_dotenv(_own_env)
elif _rag_env.exists():
    load_dotenv(_rag_env)

# 将 rag_pipeline 加入 sys.path，便于直接复用其模块
_rag_path = str(RAG_PIPELINE_DIR.resolve())
if _rag_path not in sys.path:
    sys.path.insert(0, _rag_path)

# ─────────────────────────────────────────────
# Embedding / LLM
# ─────────────────────────────────────────────
EMBEDDING_PROVIDER: str = os.getenv("EMBEDDING_PROVIDER", "dashscope")
DASHSCOPE_API_KEY: str = os.getenv("DASHSCOPE_API_KEY", "")
DASHSCOPE_BASE_URL: str = os.getenv("DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
DASHSCOPE_EMBEDDING_MODEL: str = os.getenv("DASHSCOPE_EMBEDDING_MODEL", "text-embedding-v3")

LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "dashscope")
LLM_MODEL_ID: str = os.getenv("LLM_MODEL_ID", "qwen-plus")
DEEPSEEK_API_KEY: str = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL: str = "https://api.deepseek.com/v1"

# ─────────────────────────────────────────────
# 检索参数
# ─────────────────────────────────────────────
RETRIEVAL_TOP_K: int = int(os.getenv("RETRIEVAL_TOP_K", "5"))
VECTOR_WEIGHT: float = float(os.getenv("VECTOR_WEIGHT", "0.6"))
BM25_WEIGHT: float = float(os.getenv("BM25_WEIGHT", "0.4"))
KG_TOP_K: int = int(os.getenv("KG_TOP_K", "5"))
KG_CONTEXT_WINDOW: int = int(os.getenv("KG_CONTEXT_WINDOW", "200"))  # 实体周围取原文字符数

MAX_REWRITE_ATTEMPTS: int = int(os.getenv("MAX_REWRITE_ATTEMPTS", "2"))

# ─────────────────────────────────────────────
# 路径
# ─────────────────────────────────────────────
CHROMA_PERSIST_DIR: Path = Path(
    os.getenv("CHROMA_PERSIST_DIR", str(RAG_PIPELINE_DIR / "chroma_db"))
).resolve()

LANGEXTRACT_OUTPUT_DIR: Path = Path(
    os.getenv("LANGEXTRACT_OUTPUT_DIR", str(BASE_DIR / "../langextract_pipeline/output"))
).resolve()

MINERU_OUTPUT_DIR: Path = Path(
    os.getenv("MINERU_OUTPUT_DIR", str(BASE_DIR / "../mineru_parser/output"))
).resolve()
