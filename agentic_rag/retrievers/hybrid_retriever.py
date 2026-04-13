"""Hybrid 检索器封装。

复用 rag_pipeline 的 EnsembleRetriever（Chroma 向量 + BM25），
config.py 已将 rag_pipeline 加入 sys.path。
"""

from __future__ import annotations

from langchain_core.documents import Document

import config  # agentic_rag/config.py（已设置 sys.path）


def get_hybrid_retriever(top_k: int = config.RETRIEVAL_TOP_K):
    """加载并返回 rag_pipeline 的 EnsembleRetriever。"""
    # 导入 rag_pipeline 模块（通过 sys.path 注入）
    from retriever import create_hybrid_retriever  # noqa: PLC0415
    return create_hybrid_retriever(top_k=top_k)


def retrieve_passages(query: str, top_k: int = config.RETRIEVAL_TOP_K) -> list[Document]:
    """执行 Hybrid 检索，返回段落 Document 列表。"""
    retriever = get_hybrid_retriever(top_k=top_k)
    return retriever.invoke(query)


def format_passages_for_prompt(docs: list[Document]) -> str:
    """将段落 Document 列表格式化为 Prompt 上下文字符串。"""
    if not docs:
        return "（无相关文档段落）"

    import json
    parts = []
    for i, doc in enumerate(docs, 1):
        meta = doc.metadata
        entities = json.loads(meta.get("entities", "[]"))
        header = (
            f"[段落 {i}] 文档：{meta.get('document_id', '?')}"
            f"  章节：{meta.get('section_title', '?')}"
            f"  (p.{meta.get('page_idx', '?')}, type={meta.get('chunk_type', '?')})"
        )
        if entities:
            header += f"\n  相关实体：{', '.join(entities[:4])}"
        parts.append(f"{header}\n{doc.page_content[:500]}")
    return "\n\n---\n\n".join(parts)
