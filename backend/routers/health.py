"""健康检查路由。"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
import config
from database import count_by_status
from models import HealthResponse, HealthComponents, DocumentStats

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health_check():
    components = await _check_components()
    stats_raw = await count_by_status()
    stats = DocumentStats(**stats_raw)

    all_ok = all(v == "ok" for v in components.dict().values())
    status = "ok" if all_ok else "degraded"

    return HealthResponse(
        status=status,
        timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        components=components,
        document_stats=stats,
    )


async def _check_components() -> HealthComponents:
    return HealthComponents(
        database=await _check_database(),
        chroma_db=_check_chroma(),
        kg_jsonl=_check_kg_jsonl(),
        mineru_api=await _check_mineru_api(),
        agentic_rag=_check_agentic_rag(),
    )


async def _check_database() -> str:
    try:
        await count_by_status()
        return "ok"
    except Exception:
        return "error"


def _check_chroma() -> str:
    try:
        from core.indexer import index_exists
        if index_exists(config.CHROMA_PERSIST_DIR):
            from core.indexer import load_index
            load_index(config.CHROMA_PERSIST_DIR)
        return "ok"
    except FileNotFoundError:
        return "ok"  # 未构建索引不算错误
    except Exception:
        return "error"


def _check_kg_jsonl() -> str:
    try:
        if config.KG_OUTPUT_DIR.exists():
            count = len(list(config.KG_OUTPUT_DIR.glob("*.jsonl")))
            return "ok"
        return "ok"
    except Exception:
        return "error"


async def _check_mineru_api() -> str:
    if not config.MINERU_API_TOKEN:
        return "error"
    try:
        import httpx
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(
                f"{config.MINERU_BASE_URL}/api/v4/extract-results/batch/health-check",
                headers={"Authorization": f"Bearer {config.MINERU_API_TOKEN}"},
            )
            # 任何响应（包括 404）都说明 API 可达
            return "ok"
    except Exception:
        return "error"


def _check_agentic_rag() -> str:
    try:
        from core.rag_graph import _create_llm
        _create_llm()
        return "ok"
    except Exception:
        return "error"
