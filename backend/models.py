"""Pydantic 请求/响应模型。"""

from __future__ import annotations
from typing import Dict, List, Optional
from pydantic import BaseModel, Field


# ── 文档管理 ──────────────────────────────────────────────────────

class UploadResponse(BaseModel):
    doc_id: str
    filename: str
    file_type: str
    status: str
    message: str


class DocumentStatus(BaseModel):
    doc_id: str
    filename: str
    file_type: str
    status: str
    vector_status: str
    kg_status: str
    chunk_count: Optional[int] = None
    entity_count: Optional[int] = None
    error_msg: Optional[str] = None
    created_at: str
    updated_at: str
    ready_for_qa: bool


class DocumentListItem(BaseModel):
    doc_id: str
    filename: str
    file_type: str
    status: str
    chunk_count: Optional[int] = None
    entity_count: Optional[int] = None
    created_at: str


class DocumentListResponse(BaseModel):
    total: int
    limit: int
    offset: int
    documents: List[DocumentListItem]


class DeleteResponse(BaseModel):
    message: str
    doc_id: str


# ── Q&A ──────────────────────────────────────────────────────────

class QARequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=500)
    doc_ids: Optional[List[str]] = None
    session_id: Optional[str] = None


class KGEntity(BaseModel):
    name: str
    type: str
    attributes: Dict[str, str]
    context_snippet: str
    document_id: str


class PassageSource(BaseModel):
    content: str
    section: str
    page: int
    document_id: str
    chunk_type: str
    entities: List[str]
    char_range: List[int]


class QAMeta(BaseModel):
    route: str
    rewrite_count: int
    question_used: str
    original_question: str
    sufficient: bool
    latency_ms: int


class QASources(BaseModel):
    kg_entities: List[KGEntity]
    passages: List[PassageSource]


class QAResponse(BaseModel):
    answer: str
    meta: QAMeta
    sources: QASources
    session_id: Optional[str] = None


# ── 健康检查 ──────────────────────────────────────────────────────

class HealthComponents(BaseModel):
    database: str
    chroma_db: str
    kg_jsonl: str
    mineru_api: str
    agentic_rag: str


class DocumentStats(BaseModel):
    total: int
    ready: int
    indexing: int
    parsing: int
    failed: int


class HealthResponse(BaseModel):
    status: str
    timestamp: str
    components: HealthComponents
    document_stats: DocumentStats


# ── 错误响应 ──────────────────────────────────────────────────────

class ErrorResponse(BaseModel):
    error: str
    message: str
    doc_id: Optional[str] = None
    detail: Optional[str] = None
