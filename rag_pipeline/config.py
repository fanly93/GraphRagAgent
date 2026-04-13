"""RAG Pipeline 配置加载。"""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR / ".env")

# ─────────────────────────────────────────────
# Embedding
# ─────────────────────────────────────────────

EMBEDDING_PROVIDER: str = os.getenv("EMBEDDING_PROVIDER", "dashscope")
DASHSCOPE_API_KEY: str = os.getenv("DASHSCOPE_API_KEY", "")
DASHSCOPE_BASE_URL: str = os.getenv("DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
DASHSCOPE_EMBEDDING_MODEL: str = os.getenv("DASHSCOPE_EMBEDDING_MODEL", "text-embedding-v3")

OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
OPENAI_EMBEDDING_MODEL: str = "text-embedding-3-large"

# ─────────────────────────────────────────────
# LLM（生成阶段）
# ─────────────────────────────────────────────

LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "dashscope")
LLM_MODEL_ID: str = os.getenv("LLM_MODEL_ID", "qwen-plus")
DEEPSEEK_API_KEY: str = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL: str = "https://api.deepseek.com/v1"

# ─────────────────────────────────────────────
# 索引参数
# ─────────────────────────────────────────────

CHUNK_SIZE: int = int(os.getenv("CHUNK_SIZE", "500"))
CHUNK_OVERLAP: int = int(os.getenv("CHUNK_OVERLAP", "80"))
MIN_CHUNK_SIZE: int = int(os.getenv("MIN_CHUNK_SIZE", "50"))

CHROMA_PERSIST_DIR: Path = Path(
    os.getenv("CHROMA_PERSIST_DIR", str(BASE_DIR / "chroma_db"))
)

# ─────────────────────────────────────────────
# 检索参数
# ─────────────────────────────────────────────

VECTOR_WEIGHT: float = float(os.getenv("VECTOR_WEIGHT", "0.6"))
BM25_WEIGHT: float = float(os.getenv("BM25_WEIGHT", "0.4"))
RETRIEVAL_TOP_K: int = int(os.getenv("RETRIEVAL_TOP_K", "4"))

# ─────────────────────────────────────────────
# 路径
# ─────────────────────────────────────────────

MINERU_OUTPUT_DIR: Path = Path(
    os.getenv("MINERU_OUTPUT_DIR", str(BASE_DIR / "../mineru_parser/output"))
).resolve()

LANGEXTRACT_OUTPUT_DIR: Path = Path(
    os.getenv("LANGEXTRACT_OUTPUT_DIR", str(BASE_DIR / "../langextract_pipeline/output"))
).resolve()


def validate():
    """启动前检查关键配置。"""
    if EMBEDDING_PROVIDER == "dashscope" and not DASHSCOPE_API_KEY:
        raise ValueError("DASHSCOPE_API_KEY 未配置，请在 .env 中填写。")
    if EMBEDDING_PROVIDER == "openai" and not OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY 未配置，请在 .env 中填写。")
    if not MINERU_OUTPUT_DIR.exists():
        raise ValueError(f"MinerU 输出目录不存在：{MINERU_OUTPUT_DIR}")
