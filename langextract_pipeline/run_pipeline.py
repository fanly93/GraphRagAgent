"""LangExtract 知识图谱抽取 Pipeline 主入口。

完整流程：
  MinerU 解析结果读取
    → LangExtract 实体/关系抽取（DashScope / DeepSeek）
    → JSONL 结果保存
    → 可视化 HTML 生成
    → 控制台摘要输出

用法：
    # 处理所有 MinerU 已解析文档
    python run_pipeline.py

    # 只处理指定文档（目录名，可多个）
    python run_pipeline.py "0.LangChain技术生态介绍" "销售数据统计"

    # dry-run：只读取文档，不调用 API
    python run_pipeline.py --dry-run
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import langextract as lx

import config
import kg_prompts
import mineru_reader
import providers


# ─────────────────────────────────────────────
# 结果处理工具
# ─────────────────────────────────────────────

def _is_single_doc(result) -> bool:
    return isinstance(result, lx.data.AnnotatedDocument)


def _to_list(result) -> list[lx.data.AnnotatedDocument]:
    """统一为列表，兼容单文档和多文档返回值。"""
    if _is_single_doc(result):
        return [result]
    return list(result)


def _print_extraction_summary(docs: list[lx.data.AnnotatedDocument]) -> None:
    """打印抽取结果摘要。"""
    total_extractions = 0
    total_grounded = 0

    for doc in docs:
        extractions = doc.extractions or []
        grounded = [e for e in extractions if e.char_interval]
        total_extractions += len(extractions)
        total_grounded += len(grounded)

        print(f"\n  [{doc.document_id}]")
        print(f"    抽取总数: {len(extractions)}  |  有效定位（grounded）: {len(grounded)}")

        # 按类型汇总
        from collections import Counter
        class_counts = Counter(e.extraction_class for e in grounded)
        for cls, cnt in sorted(class_counts.items()):
            print(f"    {cls:15s}: {cnt}")

        # 打印前 5 条
        if grounded:
            print("    前 5 条抽取结果：")
            for e in grounded[:5]:
                span = (doc.text or "")[
                    e.char_interval.start_pos:e.char_interval.end_pos
                ]
                attrs_str = ", ".join(f"{k}={v}" for k, v in (e.attributes or {}).items())
                print(f"      [{e.extraction_class}] '{span}'  {attrs_str}")

    print(f"\n  合计：{len(docs)} 篇文档 | {total_extractions} 条抽取 | "
          f"{total_grounded} 条有效定位 "
          f"({total_grounded / total_extractions * 100:.1f}% 定位率)"
          if total_extractions else "  合计：无抽取结果")


def _save_results(
    docs: list[lx.data.AnnotatedDocument],
    output_name: str,
) -> tuple[Path, Path]:
    """保存 JSONL + HTML 可视化文件，返回两个文件路径。

    output_name 不含扩展名（如 kg_extraction_20260413_120000）。
    实际保存为 output_name.jsonl，HTML 为 output_name.html。
    """
    jsonl_name = f"{output_name}.jsonl"
    jsonl_path = config.OUTPUT_DIR / jsonl_name
    html_path = config.OUTPUT_DIR / f"{output_name}.html"

    # 保存 JSONL（output_name 含 .jsonl 后缀，save_annotated_documents 直接用作文件名）
    lx.io.save_annotated_documents(
        docs,
        output_name=jsonl_name,
        output_dir=str(config.OUTPUT_DIR),
    )

    # 生成 HTML 可视化（传入 .jsonl 文件实际路径）
    try:
        html_content = lx.visualize(str(jsonl_path))
        html_str = html_content.data if hasattr(html_content, "data") else html_content
        html_path.write_text(html_str, encoding="utf-8")
        print(f"\n  [已保存] JSONL → {jsonl_path}")
        print(f"  [已保存] HTML  → {html_path}")
    except Exception as e:
        print(f"\n  [已保存] JSONL → {jsonl_path}")
        print(f"  [警告]   HTML 生成失败：{e}")

    return jsonl_path, html_path


# ─────────────────────────────────────────────
# 主流程
# ─────────────────────────────────────────────

def run(
    doc_filter: list[str] | None = None,
    dry_run: bool = False,
) -> None:
    """
    执行完整 pipeline。

    Args:
        doc_filter: 仅处理指定文档名（None = 处理全部）
        dry_run: True 时只读取文档，不调用 LLM API
    """
    print("=" * 60)
    print("LangExtract 知识图谱抽取 Pipeline")
    print("=" * 60)

    # ① 配置校验
    if not dry_run:
        config.validate()

    # ② 读取 MinerU 文档
    print(f"\n[1/4] 读取 MinerU 解析结果 ({config.MINERU_OUTPUT_DIR})")
    print("-" * 40)
    documents = mineru_reader.scan_mineru_outputs(
        config.MINERU_OUTPUT_DIR,
        doc_filter=doc_filter,
        include_tables=True,
    )

    if not documents:
        print("  未找到可读取的文档，请检查 MINERU_OUTPUT_DIR 配置。")
        return

    print(f"\n  共读取 {len(documents)} 篇文档")

    if dry_run:
        print("\n[dry-run 模式] 仅读取文档，跳过 API 调用。")
        for doc in documents:
            mineru_reader.preview_document(doc)
            print()
        return

    # ③ 构建模型
    print(f"\n[2/4] 初始化模型 (provider={config.KG_MODEL_PROVIDER})")
    print("-" * 40)
    model = providers.create_model()
    print(f"  MAX_CHAR_BUFFER={config.MAX_CHAR_BUFFER}  "
          f"MAX_WORKERS={config.MAX_WORKERS}  "
          f"PASSES={config.EXTRACTION_PASSES}")

    # ④ 执行抽取
    print(f"\n[3/4] 执行知识图谱抽取")
    print("-" * 40)
    start_time = time.time()

    result = lx.extract(
        text_or_documents=documents,
        model=model,
        max_char_buffer=config.MAX_CHAR_BUFFER,
        batch_length=config.BATCH_LENGTH,
        max_workers=config.MAX_WORKERS,
        extraction_passes=config.EXTRACTION_PASSES,
        context_window_chars=config.CONTEXT_WINDOW_CHARS,
        **kg_prompts.KG_EXTRACT_PARAMS,
    )

    elapsed = time.time() - start_time
    result_docs = _to_list(result)
    print(f"\n  抽取完成，耗时 {elapsed:.1f}s")

    # ⑤ 打印摘要 & 保存
    print(f"\n[4/4] 结果汇总 & 保存")
    print("-" * 40)
    _print_extraction_summary(result_docs)

    # 用时间戳命名输出文件，避免覆盖
    ts = time.strftime("%Y%m%d_%H%M%S")
    output_name = f"kg_extraction_{ts}"
    _save_results(result_docs, output_name)

    print("\n" + "=" * 60)
    print("Pipeline 完成")
    print("=" * 60)


# ─────────────────────────────────────────────
# CLI 入口
# ─────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="LangExtract 知识图谱抽取 Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "docs",
        nargs="*",
        metavar="DOC_NAME",
        help="要处理的文档目录名（不填则处理全部）",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只读取文档预览，不调用 LLM API",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    run(
        doc_filter=args.docs or None,
        dry_run=args.dry_run,
    )
