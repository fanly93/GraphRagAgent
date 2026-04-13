"""Hybrid 检索器：向量检索 + BM25 关键词检索。

架构：
  EnsembleRetriever
    ├── Chroma.as_retriever()     权重 VECTOR_WEIGHT（默认 0.6）语义相似度
    └── BM25Retriever             权重 BM25_WEIGHT（默认 0.4）  精确关键词

两路检索结果通过 Reciprocal Rank Fusion (RRF) 合并，保证：
  - 语义相近但用词不同的段落被语义检索命中
  - 专有名词、术语精确匹配被 BM25 命中

后续扩展（LlamaIndex）：
  可将此文件替换为 LlamaIndex QueryFusionRetriever，保持相同的 .invoke() 接口。
"""

from __future__ import annotations

import json

from langchain_classic.retrievers import EnsembleRetriever
from langchain_chroma import Chroma
from langchain_community.retrievers import BM25Retriever
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever

import config
from indexer import load_index


def create_hybrid_retriever(
    persist_dir=config.CHROMA_PERSIST_DIR,
    top_k: int = config.RETRIEVAL_TOP_K,
    vector_weight: float = config.VECTOR_WEIGHT,
    bm25_weight: float = config.BM25_WEIGHT,
) -> EnsembleRetriever:
    """构建 Hybrid 检索器（向量 + BM25）。

    Args:
        persist_dir: Chroma 持久化目录
        top_k: 每路检索返回的最大文档数
        vector_weight: 向量检索权重
        bm25_weight: BM25 检索权重

    Returns:
        EnsembleRetriever 实例，调用 .invoke(query) 返回 list[Document]
    """
    vectorstore, documents = load_index(persist_dir)

    # 向量检索器
    vector_retriever = vectorstore.as_retriever(
        search_type="similarity",
        search_kwargs={"k": top_k},
    )

    # BM25 关键词检索器
    bm25_retriever = BM25Retriever.from_documents(documents)
    bm25_retriever.k = top_k

    # Ensemble（RRF 融合）
    ensemble = EnsembleRetriever(
        retrievers=[vector_retriever, bm25_retriever],
        weights=[vector_weight, bm25_weight],
    )

    print(f"  [Retriever] Hybrid  vector:{vector_weight}  bm25:{bm25_weight}  top_k={top_k}")
    return ensemble


def create_vector_only_retriever(
    persist_dir=config.CHROMA_PERSIST_DIR,
    top_k: int = config.RETRIEVAL_TOP_K,
) -> BaseRetriever:
    """仅向量检索（用于对比测试）。"""
    vectorstore, _ = load_index(persist_dir)
    return vectorstore.as_retriever(
        search_type="similarity",
        search_kwargs={"k": top_k},
    )


def format_retrieved_docs(docs: list[Document]) -> str:
    """将检索到的 Documents 格式化为 LLM prompt 上下文字符串。"""
    parts = []
    for i, doc in enumerate(docs, 1):
        meta = doc.metadata
        header = f"[{i}] 文档：{meta.get('document_id', '?')}  章节：{meta.get('section_title', '?')}"
        if meta.get("chunk_type") == "table":
            header += f"（表格）"
        entities = json.loads(meta.get("entities", "[]"))
        if entities:
            header += f"\n    相关实体：{', '.join(entities[:5])}"
        parts.append(f"{header}\n{doc.page_content}")
    return "\n\n---\n\n".join(parts)
