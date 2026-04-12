"""从 .env 加载运行时配置。"""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR / ".env")

# ── API 认证 ───────────────────────────────────────────────
MINERU_API_TOKEN: str = os.getenv("MINERU_API_TOKEN", "")
MINERU_BASE_URL: str = os.getenv("MINERU_BASE_URL", "https://mineru.net").rstrip("/")

# ── 解析参数默认值 ─────────────────────────────────────────
MODEL_VERSION: str = os.getenv("MINERU_MODEL_VERSION", "vlm")
LANGUAGE: str = os.getenv("MINERU_LANGUAGE", "ch")
ENABLE_TABLE: bool = os.getenv("MINERU_ENABLE_TABLE", "true").lower() == "true"
ENABLE_FORMULA: bool = os.getenv("MINERU_ENABLE_FORMULA", "true").lower() == "true"
IS_OCR: bool = os.getenv("MINERU_IS_OCR", "false").lower() == "true"

# ── 轮询 ──────────────────────────────────────────────────
POLL_INTERVAL: int = int(os.getenv("POLL_INTERVAL_SECONDS", "10"))
POLL_TIMEOUT: int = int(os.getenv("POLL_TIMEOUT_SECONDS", "600"))

# ── 本地路径 ──────────────────────────────────────────────
INPUT_DIR: Path = BASE_DIR / "input"
OUTPUT_DIR: Path = BASE_DIR / "output"

# ── 文件格式路由规则 ──────────────────────────────────────
# 精准解析 API 支持的扩展名
PRECISE_API_EXTENSIONS: frozenset[str] = frozenset({
    ".pdf",
    ".doc", ".docx",
    ".ppt", ".pptx",
    ".html",
    ".png", ".jpg", ".jpeg", ".jp2", ".webp", ".gif", ".bmp",
})

# Agent 轻量 API 支持的扩展名（Excel 专用）
AGENT_API_EXTENSIONS: frozenset[str] = frozenset({
    ".xls", ".xlsx",
})

ALL_SUPPORTED_EXTENSIONS: frozenset[str] = PRECISE_API_EXTENSIONS | AGENT_API_EXTENSIONS
