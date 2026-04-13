"""Hybrid 检索器（Chroma 向量 + BM25 关键词，RRF 融合）。"""

from __future__ import annotations

import json
from pathlib import Path

from langchain_core.documents import Document

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
import config
from core.indexer import load_index


def create_hybrid_retriever(
    persist_dir: Path = config.CHROMA_PERSIST_DIR,
    top_k: int = config.RETRIEVAL_TOP_K,
    vector_weight: float = config.VECTOR_WEIGHT,
    bm25_weight: float = config.BM25_WEIGHT,
    doc_ids: list[str] | None = None,
):
    """构建 Hybrid 检索器，返回 EnsembleRetriever。"""
    from langchain_classic.retrievers import EnsembleRetriever
    from langchain_community.retrievers import BM25Retriever

    vectorstore, documents = load_index(persist_dir)

    # 按 doc_ids 过滤（若指定）
    if doc_ids:
        doc_id_set = set(doc_ids)
        documents = [d for d in documents if d.metadata.get("document_id") in doc_id_set]

    if not documents:
        raise ValueError("没有可检索的文档，请先上传并等待索引构建完成")

    # 按 doc_ids 过滤 vectorstore（通过 search_kwargs filter）
    search_kwargs: dict = {"k": top_k}
    if doc_ids:
        search_kwargs["filter"] = {"document_id": {"$in": doc_ids}}

    vector_retriever = vectorstore.as_retriever(
        search_type="similarity",
        search_kwargs=search_kwargs,
    )

    bm25_retriever = BM25Retriever.from_documents(documents)
    bm25_retriever.k = top_k

    ensemble = EnsembleRetriever(
        retrievers=[vector_retriever, bm25_retriever],
        weights=[vector_weight, bm25_weight],
    )
    return ensemble


def retrieve_passages(
    query: str,
    top_k: int = config.RETRIEVAL_TOP_K,
    doc_ids: list[str] | None = None,
) -> list[Document]:
    retriever = create_hybrid_retriever(top_k=top_k, doc_ids=doc_ids)
    return retriever.invoke(query)


def format_passages_for_prompt(docs: list[Document]) -> str:
    if not docs:
        return "（无相关文档段落）"
    parts = []
    for i, doc in enumerate(docs, 1):
        meta = doc.metadata
        try:
            entities = json.loads(meta.get("entities", "[]"))
        except Exception:
            entities = []
        header = (
            f"[段落 {i}] 文档：{meta.get('document_id', '?')}"
            f"  章节：{meta.get('section_title', '?')}"
            f"  (p.{meta.get('page_idx', '?')}, type={meta.get('chunk_type', '?')})"
        )
        if entities:
            header += f"\n  相关实体：{', '.join(entities[:4])}"
        parts.append(f"{header}\n{doc.page_content[:600]}")
    return "\n\n---\n\n".join(parts)
