"""后端服务配置加载。"""

import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent

_env_file = BASE_DIR / ".env"
if _env_file.exists():
    load_dotenv(_env_file)

# ── MinerU ────────────────────────────────────────────────────────
MINERU_API_TOKEN: str = os.getenv("MINERU_API_TOKEN", "")
MINERU_BASE_URL: str = os.getenv("MINERU_BASE_URL", "https://mineru.net")

# ── LLM ──────────────────────────────────────────────────────────
LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "dashscope")
LLM_MODEL_ID: str = os.getenv("LLM_MODEL_ID", "qwen-plus")
DASHSCOPE_API_KEY: str = os.getenv("DASHSCOPE_API_KEY", "")
DASHSCOPE_BASE_URL: str = os.getenv(
    "DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"
)
DASHSCOPE_EMBEDDING_MODEL: str = os.getenv("DASHSCOPE_EMBEDDING_MODEL", "text-embedding-v3")
DEEPSEEK_API_KEY: str = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL: str = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")

# ── 路径 ──────────────────────────────────────────────────────────
UPLOAD_DIR: Path = Path(os.getenv("UPLOAD_DIR", str(BASE_DIR / "uploads"))).resolve()
DB_PATH: Path = Path(os.getenv("DB_PATH", str(BASE_DIR / "data/jobs.db"))).resolve()
MINERU_OUTPUT_DIR: Path = Path(os.getenv("MINERU_OUTPUT_DIR", str(BASE_DIR / "output"))).resolve()
CHROMA_PERSIST_DIR: Path = Path(os.getenv("CHROMA_PERSIST_DIR", str(BASE_DIR / "chroma_db"))).resolve()
KG_OUTPUT_DIR: Path = Path(os.getenv("KG_OUTPUT_DIR", str(BASE_DIR / "kg_output"))).resolve()

# ── 服务参数 ──────────────────────────────────────────────────────
PORT: int = int(os.getenv("PORT", "8000"))
DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"
MAX_UPLOAD_SIZE_MB: int = int(os.getenv("MAX_UPLOAD_SIZE_MB", "200"))
POLL_INTERVAL_SEC: int = int(os.getenv("POLL_INTERVAL_SEC", "10"))
POLL_TIMEOUT_SEC: int = int(os.getenv("POLL_TIMEOUT_SEC", "600"))
QA_TIMEOUT_SEC: int = int(os.getenv("QA_TIMEOUT_SEC", "120"))

# ── 检索参数 ──────────────────────────────────────────────────────
RETRIEVAL_TOP_K: int = int(os.getenv("RETRIEVAL_TOP_K", "5"))
VECTOR_WEIGHT: float = float(os.getenv("VECTOR_WEIGHT", "0.6"))
BM25_WEIGHT: float = float(os.getenv("BM25_WEIGHT", "0.4"))
KG_TOP_K: int = int(os.getenv("KG_TOP_K", "5"))
KG_CONTEXT_WINDOW: int = int(os.getenv("KG_CONTEXT_WINDOW", "200"))
MAX_REWRITE_ATTEMPTS: int = int(os.getenv("MAX_REWRITE_ATTEMPTS", "2"))

# ── 索引参数 ──────────────────────────────────────────────────────
CHUNK_SIZE: int = int(os.getenv("CHUNK_SIZE", "500"))
CHUNK_OVERLAP: int = int(os.getenv("CHUNK_OVERLAP", "50"))

# ── 支持格式 ──────────────────────────────────────────────────────
PRECISION_EXTENSIONS = {"pdf", "doc", "docx", "ppt", "pptx", "jpg", "jpeg", "png", "gif", "webp", "html", "htm"}
AGENT_EXTENSIONS = {"xls", "xlsx"}
ALL_SUPPORTED_EXTENSIONS = PRECISION_EXTENSIONS | AGENT_EXTENSIONS

MAX_UPLOAD_BYTES = MAX_UPLOAD_SIZE_MB * 1024 * 1024
MAX_EXCEL_BYTES = 10 * 1024 * 1024

# 确保目录存在
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
MINERU_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
CHROMA_PERSIST_DIR.mkdir(parents=True, exist_ok=True)
KG_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
