"""向量索引构建与持久化。

索引架构：
  - Chroma（向量库）：语义相似度检索，持久化到 chroma_db/
  - BM25（关键词库）：精确词项匹配，内存存储（随 Documents 重建）

持久化策略：
  - Chroma：写入磁盘，支持增量更新（collection 按 document_id 去重）
  - BM25：每次加载时从 Chroma 已有 documents 重建（无需单独持久化）

后续扩展（LlamaIndex）：
  可在此添加 LlamaIndexIndexer，实现相同的 build / load 接口。
"""

from __future__ import annotations

import json
import pickle
from pathlib import Path
from typing import Optional

from langchain_chroma import Chroma
from langchain_community.retrievers import BM25Retriever
from langchain_core.documents import Document

import config
from embeddings import create_embeddings

COLLECTION_NAME = "graphrag_docs"
BM25_CACHE_PATH = config.CHROMA_PERSIST_DIR / "bm25_docs.pkl"


# ─────────────────────────────────────────────
# 构建索引
# ─────────────────────────────────────────────

def build_index(
    documents: list[Document],
    persist_dir: Path = config.CHROMA_PERSIST_DIR,
    force_rebuild: bool = False,
) -> Chroma:
    """将 Document 列表索引到 Chroma，并缓存 BM25 语料。

    Args:
        documents: 结构感知切分后的 Document 列表
        persist_dir: Chroma 持久化目录
        force_rebuild: True 时清空旧索引重建

    Returns:
        Chroma 向量库实例
    """
    persist_dir.mkdir(parents=True, exist_ok=True)
    embeddings = create_embeddings()

    if force_rebuild:
        print("  [索引] 强制重建，清空旧数据...")
        import shutil
        if persist_dir.exists():
            shutil.rmtree(persist_dir)
        persist_dir.mkdir(parents=True, exist_ok=True)

    print(f"  [索引] 向量化 {len(documents)} 个 chunks → Chroma ({persist_dir})")
    vectorstore = Chroma.from_documents(
        documents=documents,
        embedding=embeddings,
        collection_name=COLLECTION_NAME,
        persist_directory=str(persist_dir),
    )

    # 缓存 BM25 语料（序列化 documents 用于下次 load 时重建）
    with open(BM25_CACHE_PATH, "wb") as f:
        pickle.dump(documents, f)
    print(f"  [索引] BM25 语料已缓存 ({len(documents)} docs)")

    return vectorstore


# ─────────────────────────────────────────────
# 加载索引
# ─────────────────────────────────────────────

def load_index(
    persist_dir: Path = config.CHROMA_PERSIST_DIR,
) -> tuple[Chroma, list[Document]]:
    """从磁盘加载 Chroma 向量库和 BM25 语料。

    Returns:
        (Chroma 实例, documents 列表)

    Raises:
        FileNotFoundError: 若索引不存在（需先 build_index）
    """
    if not persist_dir.exists() or not BM25_CACHE_PATH.exists():
        raise FileNotFoundError(
            f"索引不存在，请先运行 build_index。期望路径：{persist_dir}"
        )

    embeddings = create_embeddings()
    vectorstore = Chroma(
        collection_name=COLLECTION_NAME,
        embedding_function=embeddings,
        persist_directory=str(persist_dir),
    )

    with open(BM25_CACHE_PATH, "rb") as f:
        documents: list[Document] = pickle.load(f)

    print(f"  [加载] Chroma ({vectorstore._collection.count()} chunks) + BM25 ({len(documents)} docs)")
    return vectorstore, documents


# ─────────────────────────────────────────────
# 索引信息
# ─────────────────────────────────────────────

def index_stats(persist_dir: Path = config.CHROMA_PERSIST_DIR) -> dict:
    """返回当前索引的统计信息。"""
    if not persist_dir.exists():
        return {"status": "not_built"}

    try:
        vectorstore, documents = load_index(persist_dir)
        doc_ids = list({d.metadata.get("document_id", "unknown") for d in documents})
        chunk_types = {}
        for d in documents:
            t = d.metadata.get("chunk_type", "text")
            chunk_types[t] = chunk_types.get(t, 0) + 1
        return {
            "status": "ready",
            "total_chunks": len(documents),
            "documents": sorted(doc_ids),
            "chunk_types": chunk_types,
            "chroma_count": vectorstore._collection.count(),
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}
