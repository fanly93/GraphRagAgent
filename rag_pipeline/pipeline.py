"""RAG Pipeline 主入口。

功能：
  1. build   - 扫描 MinerU 输出 → 结构感知切分 → 构建 Chroma + BM25 索引
  2. query   - 加载索引 → Hybrid 检索 → LLM 生成答案
  3. stats   - 显示索引统计信息

用法：
    python pipeline.py build                    # 索引全部文档
    python pipeline.py build "0.LangChain技术生态介绍"  # 索引指定文档
    python pipeline.py build --force            # 强制重建索引
    python pipeline.py query "LangChain是什么？"
    python pipeline.py stats
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import config
from structure_splitter import scan_and_split
from indexer import build_index, index_stats
from retriever import create_hybrid_retriever, format_retrieved_docs
from llm_provider import create_llm


# ─────────────────────────────────────────────
# 构建索引
# ─────────────────────────────────────────────

def cmd_build(doc_filter: list[str] | None = None, force: bool = False) -> None:
    """执行索引构建流程。"""
    print("=" * 60)
    print("RAG Pipeline — 索引构建")
    print("=" * 60)

    config.validate()

    print(f"\n[1/3] 结构感知文本切分")
    print(f"  MinerU 目录：{config.MINERU_OUTPUT_DIR}")
    print(f"  chunk_size={config.CHUNK_SIZE}  overlap={config.CHUNK_OVERLAP}")
    print("-" * 40)

    documents = scan_and_split(
        mineru_output_dir=config.MINERU_OUTPUT_DIR,
        doc_filter=doc_filter,
        chunk_size=config.CHUNK_SIZE,
        chunk_overlap=config.CHUNK_OVERLAP,
    )

    if not documents:
        print("  未找到可切分的文档，请检查 MINERU_OUTPUT_DIR。")
        return

    print(f"\n  共生成 {len(documents)} 个 chunks")

    print(f"\n[2/3] 构建向量索引（Chroma + BM25）")
    print("-" * 40)
    build_index(documents, force_rebuild=force)

    print(f"\n[3/3] 索引摘要")
    print("-" * 40)
    stats = index_stats()
    print(f"  状态：{stats['status']}")
    print(f"  总 chunks：{stats.get('total_chunks', 0)}")
    print(f"  文档列表：{stats.get('documents', [])}")
    print(f"  类型分布：{stats.get('chunk_types', {})}")

    print("\n" + "=" * 60)
    print("索引构建完成")
    print("=" * 60)


# ─────────────────────────────────────────────
# 查询
# ─────────────────────────────────────────────

RAG_PROMPT_TEMPLATE = """\
你是一个专业的知识问答助手。请根据以下检索到的上下文回答用户问题。

回答规则：
1. 只根据提供的上下文回答，不要凭空推测
2. 如果上下文不足以回答问题，请明确说明
3. 回答简洁准确，引用来源时注明文档名和章节

检索上下文：
{context}

用户问题：{question}

回答："""


def cmd_query(question: str, show_sources: bool = True) -> str:
    """执行 Hybrid 检索 + LLM 生成。"""
    print("=" * 60)
    print(f"查询：{question}")
    print("=" * 60)

    print(f"\n[1/3] 加载索引 + 创建 Hybrid 检索器")
    print("-" * 40)
    retriever = create_hybrid_retriever()

    print(f"\n[2/3] 检索相关段落")
    print("-" * 40)
    docs = retriever.invoke(question)
    print(f"  检索到 {len(docs)} 个相关 chunks")

    if show_sources:
        print("\n  --- 检索结果预览 ---")
        for i, doc in enumerate(docs, 1):
            meta = doc.metadata
            print(f"  [{i}] {meta.get('document_id')} / {meta.get('section_title')}"
                  f"  (p.{meta.get('page_idx', '?')}, type={meta.get('chunk_type')})")
            print(f"      {doc.page_content[:100]}...")
            entities = __import__("json").loads(meta.get("entities", "[]"))
            if entities:
                print(f"      实体：{entities[:3]}")

    print(f"\n[3/3] LLM 生成答案")
    print("-" * 40)
    llm = create_llm()
    context = format_retrieved_docs(docs)
    prompt = RAG_PROMPT_TEMPLATE.format(context=context, question=question)

    response = llm.invoke(prompt)
    answer = response.content

    print(f"\n答案：\n{answer}")
    print("\n" + "=" * 60)
    return answer


# ─────────────────────────────────────────────
# 统计
# ─────────────────────────────────────────────

def cmd_stats() -> None:
    """显示当前索引统计信息。"""
    stats = index_stats()
    print("=" * 60)
    print("RAG Pipeline — 索引统计")
    print("=" * 60)
    import json
    print(json.dumps(stats, ensure_ascii=False, indent=2))


# ─────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="RAG Pipeline — 结构感知向量 + 关键词混合检索",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    # build
    p_build = sub.add_parser("build", help="构建向量索引")
    p_build.add_argument("docs", nargs="*", metavar="DOC_NAME", help="指定文档（不填=全部）")
    p_build.add_argument("--force", action="store_true", help="强制重建索引")

    # query
    p_query = sub.add_parser("query", help="执行 RAG 查询")
    p_query.add_argument("question", help="查询问题")
    p_query.add_argument("--no-sources", action="store_true", help="不显示检索来源")

    # stats
    sub.add_parser("stats", help="显示索引统计")

    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()

    if args.cmd == "build":
        cmd_build(doc_filter=args.docs or None, force=args.force)
    elif args.cmd == "query":
        cmd_query(args.question, show_sources=not args.no_sources)
    elif args.cmd == "stats":
        cmd_stats()
