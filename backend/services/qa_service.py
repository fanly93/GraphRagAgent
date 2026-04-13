"""Agentic RAG 问答服务：封装 LangGraph 查询，格式化输出。"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Optional

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
import config
from models import QAResponse, QAMeta, QASources, KGEntity, PassageSource


async def run_query(
    question: str,
    doc_ids: Optional[list[str]] = None,
    session_id: Optional[str] = None,
) -> QAResponse:
    """执行问答，返回结构化 QAResponse。"""
    loop = asyncio.get_event_loop()
    return await asyncio.wait_for(
        loop.run_in_executor(None, _sync_run_query, question, doc_ids, session_id),
        timeout=config.QA_TIMEOUT_SEC,
    )


def _sync_run_query(
    question: str,
    doc_ids: Optional[list[str]],
    session_id: Optional[str],
) -> QAResponse:
    """同步问答执行（在线程池中运行）。"""
    from core.rag_graph import build_graph

    t0 = time.time()

    # 每次查询按 doc_ids 构建专属图（保证检索范围正确）
    app = build_graph(doc_ids=doc_ids)

    initial_state = {
        "question": question,
        "original_question": question,
        "route": "",
        "kg_results": [],
        "passage_results": [],
        "merged_context": "",
        "sufficient": False,
        "rewrite_count": 0,
        "answer": "",
        "_grade_reason": None,
        "doc_ids": doc_ids,
    }

    result = app.invoke(initial_state)
    latency = int((time.time() - t0) * 1000)

    return _format_response(result, latency, session_id)


def _format_response(result: dict, latency: int, session_id: Optional[str]) -> QAResponse:
    """将 AgentState 转换为 QAResponse。"""

    # ── Meta ──
    meta = QAMeta(
        route=result.get("route", "hybrid_query"),
        rewrite_count=result.get("rewrite_count", 0),
        question_used=result.get("question", ""),
        original_question=result.get("original_question", ""),
        sufficient=result.get("sufficient", True),
        latency_ms=latency,
    )

    # ── KG 实体 ──
    kg_entities: list[KGEntity] = []
    for r in result.get("kg_results", []):
        attrs = r.get("attributes") or {}
        if not isinstance(attrs, dict):
            attrs = {}
        attrs = {str(k): str(v) for k, v in attrs.items()}
        kg_entities.append(KGEntity(
            name=r.get("entity_text", ""),
            type=r.get("entity_class", ""),
            attributes=attrs,
            context_snippet=r.get("context_snippet", ""),
            document_id=r.get("document_id", ""),
        ))

    # ── 段落来源 ──
    passages: list[PassageSource] = []
    for doc in result.get("passage_results", []):
        meta_data = doc.metadata if hasattr(doc, "metadata") else {}
        try:
            entities = json.loads(meta_data.get("entities", "[]"))
        except Exception:
            entities = []
        char_start = meta_data.get("char_start", 0)
        char_end = meta_data.get("char_end", 0)
        passages.append(PassageSource(
            content=doc.page_content if hasattr(doc, "page_content") else str(doc),
            section=meta_data.get("section_title", ""),
            page=meta_data.get("page_idx", 0),
            document_id=meta_data.get("document_id", ""),
            chunk_type=meta_data.get("chunk_type", "text"),
            entities=entities if isinstance(entities, list) else [],
            char_range=[char_start, char_end],
        ))

    return QAResponse(
        answer=result.get("answer", ""),
        meta=meta,
        sources=QASources(kg_entities=kg_entities, passages=passages),
        session_id=session_id,
    )
