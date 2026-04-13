"""Q&A 问答路由。"""

from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import APIRouter, HTTPException

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
import config
from database import get_document, list_documents
from models import QARequest, QAResponse

router = APIRouter(prefix="/qa", tags=["qa"])


@router.post("/query", response_model=QAResponse)
async def query(req: QARequest):
    q = req.question.strip()

    # 检查 doc_ids 是否都 READY
    if req.doc_ids:
        for doc_id in req.doc_ids:
            doc = await get_document(doc_id)
            if not doc:
                raise HTTPException(
                    status_code=404,
                    detail={"error": "DOCUMENT_NOT_FOUND", "doc_id": doc_id},
                )
            if doc["status"] != "READY":
                raise HTTPException(
                    status_code=400,
                    detail={
                        "error": "DOCUMENT_NOT_READY",
                        "message": f"文档 {doc_id[:8]} 当前状态为 {doc['status']}，请等待索引构建完成后再提问",
                        "doc_id": doc_id,
                    },
                )
    else:
        # 检查是否有任何 READY 文档
        total, ready_docs = await list_documents(status_filter="READY", limit=1)
        if total == 0:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "NO_READY_DOCUMENTS",
                    "message": "当前没有状态为 READY 的文档，请先上传并等待文档处理完成",
                },
            )

    # 执行问答
    try:
        from services.qa_service import run_query
        result = await run_query(q, req.doc_ids, req.session_id)
        return result
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=504,
            detail={"error": "LLM_TIMEOUT", "message": f"问答服务响应超时（{config.QA_TIMEOUT_SEC}s），请稍后重试"},
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={"error": "INTERNAL_ERROR", "message": f"问答服务异常：{e}"},
        )
