"""读取 MinerU 解析结果，转换为 LangExtract Document 对象。

MinerU 输出目录结构（精准 API）：
    output/{文件名}/
    ├── full.md                   # 完整 Markdown 文本（所有 pipeline 必有）
    ├── {uuid}_content_list.json  # 结构化块列表（仅精准 API）
    ├── {uuid}_origin.pdf         # 原始文件副本
    ├── layout.json               # 版面布局信息
    └── images/                   # 提取的图片

读取策略：
  - 以 full.md 为主文本内容（兼容精准 API 和 Agent API 输出）
  - 可选：将 content_list.json 中的表格/公式内容补充到 additional_context
  - document_id 使用目录名（即原始文件的 stem）
"""

import json
from pathlib import Path
from typing import Optional

import langextract as lx


# ─────────────────────────────────────────────
# 单文档读取
# ─────────────────────────────────────────────

def read_mineru_document(
    output_dir: Path,
    include_tables: bool = True,
) -> Optional[lx.data.Document]:
    """从单个 MinerU 输出目录构建 LangExtract Document。

    Args:
        output_dir: MinerU 解析输出目录（含 full.md）
        include_tables: 是否将 content_list.json 中的表格 HTML 追加到文本末尾

    Returns:
        lx.data.Document，若目录中不含 full.md 则返回 None
    """
    full_md = output_dir / "full.md"
    if not full_md.exists():
        return None

    text = full_md.read_text(encoding="utf-8").strip()
    if not text:
        return None

    # 可选：从 content_list.json 追加表格文本（LangExtract 只处理纯文本）
    # 若 full.md 已含 Markdown 表格，跳过追加以避免重复
    if include_tables and not _has_markdown_tables(text):
        content_list_files = list(output_dir.glob("*_content_list.json"))
        if content_list_files:
            table_texts = _extract_table_texts(content_list_files[0])
            if table_texts:
                text += "\n\n" + "\n\n".join(table_texts)

    doc_id = output_dir.name
    if len(text) < 200:
        print(f"  [警告] {doc_id}：文本过短（{len(text)} 字符），KG 抽取内容可能极少")

    return lx.data.Document(
        text=text,
        document_id=doc_id,
        additional_context=f"来源文档：{doc_id}",
    )


def _has_markdown_tables(text: str) -> bool:
    """检测文本中是否已含 Markdown 表格（以 | 开头的行）。"""
    return any(line.strip().startswith("|") for line in text.splitlines())


def _extract_table_texts(content_list_path: Path) -> list[str]:
    """从 content_list.json 中提取表格内容，转为可读文本。

    - 表格按出现顺序编号（[表格 1], [表格 2]...）
    - 若有 table_caption，拼接在 table_body 前
    - MinerU table_body 为完整 HTML <table> 结构
    """
    try:
        with content_list_path.open(encoding="utf-8") as f:
            blocks: list[dict] = json.load(f)
    except (json.JSONDecodeError, OSError):
        return []

    table_texts = []
    table_idx = 0
    for block in blocks:
        if block.get("type") != "table":
            continue
        table_body = block.get("table_body", "")
        if not table_body:
            continue

        table_idx += 1
        caption_raw = block.get("table_caption", [])
        # caption 可能是 list[str] 或 str
        if isinstance(caption_raw, list):
            caption = " ".join(caption_raw).strip()
        else:
            caption = str(caption_raw).strip()

        if caption:
            table_texts.append(f"[表格 {table_idx}：{caption}]\n{table_body}")
        else:
            table_texts.append(f"[表格 {table_idx}]\n{table_body}")

    return table_texts


# ─────────────────────────────────────────────
# 批量扫描
# ─────────────────────────────────────────────

def scan_mineru_outputs(
    output_base_dir: Path,
    doc_filter: Optional[list[str]] = None,
    include_tables: bool = True,
) -> list[lx.data.Document]:
    """扫描 MinerU 输出根目录，返回所有可读文档列表。

    Args:
        output_base_dir: MinerU output/ 目录
        doc_filter: 若指定，只读取列表中的文档名（目录名）
        include_tables: 是否追加表格文本

    Returns:
        lx.data.Document 列表，按目录名排序
    """
    if not output_base_dir.exists():
        raise FileNotFoundError(f"MinerU 输出目录不存在：{output_base_dir}")

    subdirs = sorted(
        d for d in output_base_dir.iterdir()
        if d.is_dir() and not d.name.startswith(".")
    )

    if doc_filter:
        subdirs = [d for d in subdirs if d.name in doc_filter]

    documents: list[lx.data.Document] = []
    skipped: list[str] = []

    for subdir in subdirs:
        doc = read_mineru_document(subdir, include_tables=include_tables)
        if doc:
            documents.append(doc)
            print(f"  [读取] {subdir.name}  ({len(doc.text):,} 字符)")
        else:
            skipped.append(subdir.name)

    if skipped:
        print(f"  [跳过] 无 full.md：{skipped}")

    return documents


# ─────────────────────────────────────────────
# 调试工具
# ─────────────────────────────────────────────

def preview_document(doc: lx.data.Document, chars: int = 300) -> None:
    """打印文档预览信息，用于调试确认读取是否正确。"""
    text = doc.text or ""
    print(f"document_id : {doc.document_id}")
    print(f"text length : {len(text):,} chars")
    print(f"preview     :\n{text[:chars]}")
    if len(text) > chars:
        print("...")
