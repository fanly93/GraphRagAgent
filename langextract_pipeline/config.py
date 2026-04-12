"""LangExtract Pipeline 配置加载。"""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR / ".env")

# ─────────────────────────────────────────────
# 模型选择
# ─────────────────────────────────────────────

# 使用哪个 Provider: dashscope | deepseek
KG_MODEL_PROVIDER: str = os.getenv("KG_MODEL_PROVIDER", "dashscope")

# 具体模型 ID（由 Provider 路由至对应 base_url）
KG_MODEL_ID: str = os.getenv("KG_MODEL_ID", "qwen-plus")

# ─────────────────────────────────────────────
# API Keys & Base URLs
# ─────────────────────────────────────────────

DASHSCOPE_API_KEY: str = os.getenv("DASHSCOPE_API_KEY", "")
DASHSCOPE_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"

DEEPSEEK_API_KEY: str = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL: str = "https://api.deepseek.com/v1"

# ─────────────────────────────────────────────
# 抽取参数
# ─────────────────────────────────────────────

# 每个文本 Chunk 最大字符数（越小越精确，但 API 调用次数越多）
MAX_CHAR_BUFFER: int = int(os.getenv("MAX_CHAR_BUFFER", "3000"))

# 每批 Chunk 数量（影响并行批次大小）
BATCH_LENGTH: int = int(os.getenv("BATCH_LENGTH", "5"))

# 并行推理 Worker 数（受限于 API 并发配额，DashScope 免费额度建议 ≤ 3）
MAX_WORKERS: int = int(os.getenv("MAX_WORKERS", "3"))

# 多轮抽取 Pass 次数（>1 时合并结果以提升召回率，成倍增加 API 调用）
EXTRACTION_PASSES: int = int(os.getenv("EXTRACTION_PASSES", "1"))

# 跨 Chunk 上下文字符数（用于共指消解，None=不启用）
CONTEXT_WINDOW_CHARS: int | None = (
    int(v) if (v := os.getenv("CONTEXT_WINDOW_CHARS")) else None
)

# ─────────────────────────────────────────────
# 路径
# ─────────────────────────────────────────────

# MinerU 解析结果根目录
MINERU_OUTPUT_DIR: Path = Path(
    os.getenv("MINERU_OUTPUT_DIR", str(BASE_DIR / "../mineru_parser/output"))
).resolve()

# 本 Pipeline 的输出目录
OUTPUT_DIR: Path = BASE_DIR / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ─────────────────────────────────────────────
# 验证（启动时快速检查）
# ─────────────────────────────────────────────

def validate():
    """检查必要配置是否已填写，缺失时抛出 ValueError。"""
    if KG_MODEL_PROVIDER == "dashscope" and not DASHSCOPE_API_KEY:
        raise ValueError(
            "DASHSCOPE_API_KEY 未配置。请在 .env 文件中填写 DASHSCOPE_API_KEY。"
        )
    if KG_MODEL_PROVIDER == "deepseek" and not DEEPSEEK_API_KEY:
        raise ValueError(
            "DEEPSEEK_API_KEY 未配置。请在 .env 文件中填写 DEEPSEEK_API_KEY。"
        )
    if not MINERU_OUTPUT_DIR.exists():
        raise ValueError(
            f"MinerU 输出目录不存在：{MINERU_OUTPUT_DIR}\n"
            "请先运行 mineru_parser，或在 .env 中配置正确的 MINERU_OUTPUT_DIR。"
        )
