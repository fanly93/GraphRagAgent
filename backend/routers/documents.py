"""文档管理路由：上传、状态查询、列表、删除。"""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
import config
from database import (
    insert_document, get_document, list_documents,
    update_document, delete_document,
)
from models import (
    UploadResponse, DocumentStatus, DocumentListResponse,
    DocumentListItem, DeleteResponse,
)

router = APIRouter(prefix="/documents", tags=["documents"])


# ── 上传 ──────────────────────────────────────────────────────────

@router.post("/upload", response_model=UploadResponse, status_code=202)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    enable_ocr: bool = Form(default=True),
):
    # 格式校验
    filename = file.filename or "unknown"
    suffix = Path(filename).suffix.lstrip(".").lower()
    if suffix not in config.ALL_SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "UNSUPPORTED_FORMAT",
                "message": f"不支持的文件格式 .{suffix}，支持格式：{'/'.join(sorted(config.ALL_SUPPORTED_EXTENSIONS))}",
            },
        )

    # 大小校验
    content = await file.read()
    file_size = len(content)
    max_bytes = config.MAX_EXCEL_BYTES if suffix in config.AGENT_EXTENSIONS else config.MAX_UPLOAD_BYTES
    if file_size > max_bytes:
        limit_mb = max_bytes // (1024 * 1024)
        raise HTTPException(
            status_code=413,
            detail={
                "error": "FILE_TOO_LARGE",
                "message": f"文件大小 {file_size // (1024*1024)}MB 超过限制（{limit_mb}MB）",
            },
        )

    # 保存文件
    doc_id = str(uuid.uuid4())
    save_path = config.UPLOAD_DIR / f"{doc_id}.{suffix}"
    save_path.write_bytes(content)

    # 写入 DB
    await insert_document(doc_id, filename, suffix, status="UPLOADED")

    # 异步解析
    background_tasks.add_task(_start_parse, doc_id, save_path, suffix, enable_ocr)

    return UploadResponse(
        doc_id=doc_id,
        filename=filename,
        file_type=suffix,
        status="PARSING",
        message="文件上传成功，MinerU 解析任务已提交",
    )


async def _start_parse(doc_id: str, file_path: Path, file_type: str, enable_ocr: bool):
    from services.mineru_service import submit_parse
    await submit_parse(doc_id, file_path, file_type, enable_ocr)


# ── 状态查询 ──────────────────────────────────────────────────────

@router.get("/{doc_id}/status", response_model=DocumentStatus)
async def get_document_status(doc_id: str):
    doc = await get_document(doc_id)
    if not doc:
        raise HTTPException(
            status_code=404,
            detail={"error": "DOCUMENT_NOT_FOUND", "doc_id": doc_id},
        )
    return DocumentStatus(
        doc_id=doc["doc_id"],
        filename=doc["filename"],
        file_type=doc["file_type"],
        status=doc["status"],
        vector_status=doc["vector_status"] or "pending",
        kg_status=doc["kg_status"] or "pending",
        chunk_count=doc["chunk_count"],
        entity_count=doc["entity_count"],
        error_msg=doc["error_msg"],
        created_at=doc["created_at"],
        updated_at=doc["updated_at"],
        ready_for_qa=(doc["status"] == "READY"),
    )


# ── 列表 ──────────────────────────────────────────────────────────

@router.get("", response_model=DocumentListResponse)
async def list_all_documents(
    status: str | None = None,
    limit: int = 20,
    offset: int = 0,
):
    limit = min(max(limit, 1), 100)
    total, docs = await list_documents(status_filter=status, limit=limit, offset=offset)
    items = [
        DocumentListItem(
            doc_id=d["doc_id"],
            filename=d["filename"],
            file_type=d["file_type"],
            status=d["status"],
            chunk_count=d["chunk_count"],
            entity_count=d["entity_count"],
            created_at=d["created_at"],
        )
        for d in docs
    ]
    return DocumentListResponse(total=total, limit=limit, offset=offset, documents=items)


# ── 删除 ──────────────────────────────────────────────────────────

@router.delete("/{doc_id}", response_model=DeleteResponse)
async def delete_doc(doc_id: str):
    doc = await get_document(doc_id)
    if not doc:
        raise HTTPException(
            status_code=404,
            detail={"error": "DOCUMENT_NOT_FOUND", "doc_id": doc_id},
        )

    if doc["status"] in ("PARSING", "INDEXING"):
        raise HTTPException(
            status_code=400,
            detail={
                "error": "DOCUMENT_BUSY",
                "message": f"文档正在处理中（{doc['status']}），请等待完成后再删除",
            },
        )

    # 删除上传文件
    suffix = doc["file_type"]
    upload_file = config.UPLOAD_DIR / f"{doc_id}.{suffix}"
    if upload_file.exists():
        upload_file.unlink()

    # 删除 MinerU 输出目录
    output_dir = config.MINERU_OUTPUT_DIR / doc_id
    if output_dir.exists():
        shutil.rmtree(output_dir)

    # 删除向量索引中的 chunks
    try:
        from core.indexer import delete_doc_from_index
        delete_doc_from_index(doc_id, config.CHROMA_PERSIST_DIR)
    except Exception as e:
        print(f"  [Delete] 向量索引清理失败（忽略）：{e}")

    # 删除 KG JSONL
    try:
        from core.kg_extractor import delete_kg_file
        delete_kg_file(doc_id, config.KG_OUTPUT_DIR)
    except Exception as e:
        print(f"  [Delete] KG 文件清理失败（忽略）：{e}")

    # 删除 DB 记录
    await delete_document(doc_id)

    # 重置 RAG 图单例
    try:
        from core.rag_graph import reset_graph
        reset_graph()
    except Exception:
        pass

    return DeleteResponse(message="文档及其所有索引数据已删除", doc_id=doc_id)
