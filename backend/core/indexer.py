"""向量索引构建与加载（Chroma + BM25）。"""

from __future__ import annotations

import pickle
from pathlib import Path
from typing import Optional

from langchain_core.documents import Document

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
import config
from core.embeddings import create_embeddings

COLLECTION_NAME = "graphrag_docs"
BM25_CACHE_FILENAME = "bm25_docs.pkl"


def build_index(
    documents: list[Document],
    persist_dir: Path = config.CHROMA_PERSIST_DIR,
    doc_id: Optional[str] = None,
) -> tuple[int, "Chroma"]:
    """将 documents 写入 Chroma，缓存 BM25 语料。返回 (chunk_count, vectorstore)。"""
    from langchain_chroma import Chroma

    persist_dir.mkdir(parents=True, exist_ok=True)
    embeddings = create_embeddings()

    bm25_cache_path = persist_dir / BM25_CACHE_FILENAME

    # 若有 doc_id 指定，先删除旧的 collection 条目（增量更新）
    existing_docs: list[Document] = []
    if bm25_cache_path.exists():
        with open(bm25_cache_path, "rb") as f:
            existing_docs = pickle.load(f)
        if doc_id:
            existing_docs = [d for d in existing_docs if d.metadata.get("document_id") != doc_id]

    all_docs = existing_docs + documents

    print(f"  [Indexer] 向量化 {len(documents)} 个新 chunks (总 {len(all_docs)}) → Chroma")

    # 重建 Chroma（简单策略：全量重写）
    import shutil
    if persist_dir.exists():
        shutil.rmtree(persist_dir)
    persist_dir.mkdir(parents=True, exist_ok=True)

    vectorstore = Chroma.from_documents(
        documents=all_docs,
        embedding=embeddings,
        collection_name=COLLECTION_NAME,
        persist_directory=str(persist_dir),
    )

    bm25_cache_path = persist_dir / BM25_CACHE_FILENAME
    with open(bm25_cache_path, "wb") as f:
        pickle.dump(all_docs, f)

    print(f"  [Indexer] 完成，BM25 缓存 {len(all_docs)} docs")
    return len(documents), vectorstore


def load_index(persist_dir: Path = config.CHROMA_PERSIST_DIR):
    """加载已构建的索引，返回 (Chroma, list[Document])。"""
    from langchain_chroma import Chroma

    bm25_cache_path = persist_dir / BM25_CACHE_FILENAME
    if not persist_dir.exists() or not bm25_cache_path.exists():
        raise FileNotFoundError(f"索引不存在：{persist_dir}，请先构建索引")

    embeddings = create_embeddings()
    vectorstore = Chroma(
        collection_name=COLLECTION_NAME,
        embedding_function=embeddings,
        persist_directory=str(persist_dir),
    )

    with open(bm25_cache_path, "rb") as f:
        documents: list[Document] = pickle.load(f)

    print(f"  [Indexer] 加载 Chroma ({vectorstore._collection.count()} chunks) + BM25 ({len(documents)} docs)")
    return vectorstore, documents


def delete_doc_from_index(doc_id: str, persist_dir: Path = config.CHROMA_PERSIST_DIR) -> None:
    """从索引中删除指定 doc_id 的所有 chunks。"""
    bm25_cache_path = persist_dir / BM25_CACHE_FILENAME
    if not persist_dir.exists() or not bm25_cache_path.exists():
        return

    with open(bm25_cache_path, "rb") as f:
        all_docs: list[Document] = pickle.load(f)

    remaining = [d for d in all_docs if d.metadata.get("document_id") != doc_id]
    if len(remaining) == len(all_docs):
        return  # 无需更新

    from langchain_chroma import Chroma
    import shutil

    embeddings = create_embeddings()

    if remaining:
        import shutil as sh
        sh.rmtree(persist_dir)
        persist_dir.mkdir(parents=True, exist_ok=True)
        Chroma.from_documents(
            documents=remaining,
            embedding=embeddings,
            collection_name=COLLECTION_NAME,
            persist_directory=str(persist_dir),
        )
        bm25_cache_path = persist_dir / BM25_CACHE_FILENAME
        with open(bm25_cache_path, "wb") as f:
            pickle.dump(remaining, f)
    else:
        shutil.rmtree(persist_dir)
        persist_dir.mkdir(parents=True, exist_ok=True)

    print(f"  [Indexer] 已从索引删除 doc_id={doc_id}")


def index_exists(persist_dir: Path = config.CHROMA_PERSIST_DIR) -> bool:
    bm25_cache_path = persist_dir / BM25_CACHE_FILENAME
    return persist_dir.exists() and bm25_cache_path.exists()
