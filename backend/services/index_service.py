"""并行索引构建服务：向量索引 + KG 实体抽取。"""

from __future__ import annotations

import asyncio
import traceback
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
import config
from database import update_document, get_document


async def build_both(doc_id: str) -> None:
    """并行执行向量索引构建和 KG 实体抽取，完成后更新文档状态。"""
    await update_document(
        doc_id,
        status="INDEXING",
        vector_status="building",
        kg_status="building",
    )
    print(f"  [Index] 开始并行索引构建 doc_id={doc_id}")

    vector_result: dict = {}
    kg_result: dict = {}

    async def run_vector():
        nonlocal vector_result
        try:
            chunk_count = await _build_vector_index(doc_id)
            vector_result = {"status": "done", "chunk_count": chunk_count}
            await update_document(doc_id, vector_status="done", chunk_count=chunk_count)
            print(f"  [Index] 向量索引完成，chunks={chunk_count}")
        except Exception as e:
            err = f"向量索引构建失败：{e}"
            print(f"  [Index] {err}\n{traceback.format_exc()}")
            vector_result = {"status": "failed", "error": err}
            await update_document(doc_id, vector_status="failed")

    async def run_kg():
        nonlocal kg_result
        try:
            entity_count = await _build_kg_index(doc_id)
            kg_result = {"status": "done", "entity_count": entity_count}
            await update_document(doc_id, kg_status="done", entity_count=entity_count)
            print(f"  [Index] KG 索引完成，entities={entity_count}")
        except Exception as e:
            err = f"KG 索引构建失败：{e}"
            print(f"  [Index] {err}\n{traceback.format_exc()}")
            kg_result = {"status": "failed", "error": err}
            await update_document(doc_id, kg_status="failed")

    await asyncio.gather(run_vector(), run_kg())

    v_ok = vector_result.get("status") == "done"
    k_ok = kg_result.get("status") == "done"

    if v_ok and k_ok:
        await update_document(doc_id, status="READY")
        print(f"  [Index] doc_id={doc_id} → READY")
        # 重置 RAG graph 单例，使新索引生效
        from core.rag_graph import reset_graph
        reset_graph()
    else:
        errors = []
        if not v_ok:
            errors.append(vector_result.get("error", "向量索引失败"))
        if not k_ok:
            errors.append(kg_result.get("error", "KG 索引失败"))
        await update_document(
            doc_id,
            status="INDEX_FAILED",
            error_msg=" | ".join(errors),
        )
        print(f"  [Index] doc_id={doc_id} → INDEX_FAILED: {errors}")


async def _build_vector_index(doc_id: str) -> int:
    """构建向量索引，返回 chunk 数量。在 asyncio executor 中运行 CPU 密集任务。"""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _sync_build_vector_index, doc_id)


def _sync_build_vector_index(doc_id: str) -> int:
    """同步构建向量索引（在线程池中执行）。"""
    from core.structure_splitter import split_document
    from core.indexer import build_index

    documents = split_document(
        doc_id=doc_id,
        mineru_output_dir=config.MINERU_OUTPUT_DIR,
        kg_output_dir=config.KG_OUTPUT_DIR,
        chunk_size=config.CHUNK_SIZE,
        chunk_overlap=config.CHUNK_OVERLAP,
    )

    if not documents:
        raise ValueError(f"doc_id={doc_id} 未找到可切分内容")

    chunk_count, _ = build_index(documents, persist_dir=config.CHROMA_PERSIST_DIR, doc_id=doc_id)
    return chunk_count


async def _build_kg_index(doc_id: str) -> int:
    """构建 KG 实体索引，返回 match_exact 实体数量。"""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _sync_build_kg_index, doc_id)


def _sync_build_kg_index(doc_id: str) -> int:
    """同步构建 KG 索引（在线程池中执行）。"""
    from core.kg_extractor import build_kg_index
    from langchain_openai import ChatOpenAI

    if config.LLM_PROVIDER == "deepseek":
        llm = ChatOpenAI(
            model=config.LLM_MODEL_ID,
            api_key=config.DEEPSEEK_API_KEY,
            base_url=config.DEEPSEEK_BASE_URL,
        )
    else:
        extra_body = {}
        if "qwen3" in config.LLM_MODEL_ID.lower():
            extra_body = {"enable_thinking": False}
        llm = ChatOpenAI(
            model=config.LLM_MODEL_ID,
            api_key=config.DASHSCOPE_API_KEY,
            base_url=config.DASHSCOPE_BASE_URL,
            model_kwargs={"extra_body": extra_body} if extra_body else {},
        )

    return build_kg_index(
        doc_id=doc_id,
        mineru_output_dir=config.MINERU_OUTPUT_DIR,
        kg_output_dir=config.KG_OUTPUT_DIR,
        llm=llm,
    )
