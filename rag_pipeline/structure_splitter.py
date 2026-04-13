"""基于 MinerU content_list.json 的结构感知文本切分器。

切分策略：
  - 以标题（text_level）为语义边界，避免跨章节混合内容
  - 正文段落在同一标题下聚合，超过 CHUNK_SIZE 时再按句子边界切分
  - 短文本（< MIN_CHUNK_SIZE）不丢弃，追加到上一个 chunk 的 page_content
  - 短章节（flush 后内容不足）并入前一个 chunk，不单独成段
  - 表格独立成 chunk，保留 table_caption 作为上下文前缀
  - 跳过 discarded / image 块（无可检索文本）
  - char_start 使用顺序游标扫描（sequential find），避免重复文本定位错误
  - 与 LangExtract JSONL 交叉引用，为 chunk 打上实体元数据标签

输出：list[langchain_core.documents.Document]
  每个 Document 携带 metadata：
    document_id, section_title, section_level, page_idx,
    char_start, char_end, chunk_type, entities, entity_types
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

from langchain_core.documents import Document

import config


# ─────────────────────────────────────────────
# 内部工具
# ─────────────────────────────────────────────

def _split_text_by_sentences(text: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    """将长文本按句子边界切分为多个 chunk，保持 overlap。"""
    sentences = re.split(r'(?<=[。！？\n])|(?<=\. )', text)
    sentences = [s.strip() for s in sentences if s.strip()]

    chunks, current, current_len = [], [], 0
    for sent in sentences:
        if current_len + len(sent) > chunk_size and current:
            chunks.append("".join(current))
            overlap_buf, overlap_len = [], 0
            for s in reversed(current):
                if overlap_len + len(s) <= chunk_overlap:
                    overlap_buf.insert(0, s)
                    overlap_len += len(s)
                else:
                    break
            current = overlap_buf
            current_len = overlap_len
        current.append(sent)
        current_len += len(sent)

    if current:
        chunks.append("".join(current))
    return chunks


def _sequential_find(full_text: str, needle: str, cursor: int) -> int:
    """从 cursor 位置向后搜索 needle，返回找到的位置；找不到返回 cursor。

    使用顺序游标避免重复文本被定位到第一次出现处（问题二修复）。
    """
    if not full_text or not needle:
        return cursor
    pos = full_text.find(needle, cursor)
    if pos == -1:
        # 宽松回退：忽略空白差异，取 cursor 本身保持单调递增
        return cursor
    return pos


def _load_entity_index(doc_id: str) -> list[dict]:
    """从 LangExtract JSONL 加载该文档的 grounded 实体列表（仅 match_exact）。"""
    for jsonl_file in sorted(config.LANGEXTRACT_OUTPUT_DIR.glob("*.jsonl")):
        with open(jsonl_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                doc = json.loads(line)
                if doc.get("document_id") == doc_id:
                    return [
                        e for e in doc.get("extractions", [])
                        if e.get("char_interval") and e.get("alignment_status") == "match_exact"
                    ]
    return []


def _annotate_entities(
    char_start: int,
    char_end: int,
    entity_index: list[dict],
) -> tuple[list[str], list[str]]:
    """找出落在 [char_start, char_end) 区间内的实体名称和类型。"""
    names, types = [], []
    for e in entity_index:
        ci = e["char_interval"]
        if ci["start_pos"] >= char_start and ci["end_pos"] <= char_end:
            names.append(e["extraction_text"])
            types.append(e["extraction_class"])
    return names, types


def _make_doc(
    page_content: str,
    doc_id: str,
    section_title: str,
    section_level: int,
    page_idx: int,
    char_start: int,
    char_end: int,
    chunk_type: str,
    entity_index: list[dict],
    source: str,
    table_caption: str = "",
) -> Document:
    """统一构造 Document，序列化 entities 为 JSON 字符串（Chroma 不允许空列表）。"""
    entity_names, entity_types = _annotate_entities(char_start, char_end, entity_index)
    meta = {
        "document_id": doc_id,
        "section_title": section_title,
        "section_level": section_level,
        "page_idx": page_idx,
        "char_start": char_start,
        "char_end": char_end,
        "chunk_type": chunk_type,
        "entities": json.dumps(entity_names, ensure_ascii=False),
        "entity_types": json.dumps(entity_types, ensure_ascii=False),
        "source": source,
    }
    if chunk_type == "table":
        meta["table_caption"] = table_caption
    return Document(page_content=page_content, metadata=meta)


# ─────────────────────────────────────────────
# 主切分函数
# ─────────────────────────────────────────────

def split_document(
    doc_dir: Path,
    chunk_size: int = config.CHUNK_SIZE,
    chunk_overlap: int = config.CHUNK_OVERLAP,
    min_chunk_size: int = config.MIN_CHUNK_SIZE,
) -> list[Document]:
    """从单个 MinerU 输出目录生成结构感知 Document 列表。

    Args:
        doc_dir: MinerU 输出子目录（含 full.md 和 *_content_list.json）
        chunk_size: 目标 chunk 最大字符数
        chunk_overlap: 相邻 chunk 重叠字符数
        min_chunk_size: 小于此值的 chunk 追加到前一个 Document，不单独成段

    Returns:
        list[Document]，每个 Document 代表一个可检索语义单元
    """
    doc_id = doc_dir.name
    content_list_files = list(doc_dir.glob("*_content_list.json"))

    # ── 无 content_list.json → 降级为 full.md 直接切分 ──
    if not content_list_files:
        full_md = doc_dir / "full.md"
        if not full_md.exists():
            return []
        text = full_md.read_text(encoding="utf-8").strip()
        if not text:
            return []
        entity_index = _load_entity_index(doc_id)
        return _split_plain_text(text, doc_id, entity_index, chunk_size, chunk_overlap)

    # ── 有 content_list.json → 结构感知切分 ──
    with open(content_list_files[0], encoding="utf-8") as f:
        blocks: list[dict] = json.load(f)

    entity_index = _load_entity_index(doc_id)

    full_md = doc_dir / "full.md"
    full_text = full_md.read_text(encoding="utf-8") if full_md.exists() else ""

    documents: list[Document] = []
    current_section_title = doc_id
    current_section_level = 0

    # 用于聚合正文段落的缓冲区
    text_buffer: list[str] = []
    buffer_page: int = 0

    # 顺序游标：char_start 定位从此处向后搜索（问题二修复）
    search_cursor: int = 0

    def _append_to_last(text: str) -> None:
        """将短文本追加到最后一个 Document 的 page_content（问题一/三修复）。"""
        if not documents:
            return
        last = documents[-1]
        new_content = last.page_content + "\n" + text
        # 重新计算 char_end 和实体
        cs = last.metadata["char_start"]
        ce = cs + len(new_content)
        entity_names, entity_types = _annotate_entities(cs, ce, entity_index)
        documents[-1] = Document(
            page_content=new_content,
            metadata={
                **last.metadata,
                "char_end": ce,
                "entities": json.dumps(entity_names, ensure_ascii=False),
                "entity_types": json.dumps(entity_types, ensure_ascii=False),
            },
        )

    def _flush_buffer() -> None:
        """将文本缓冲区切分并生成 Documents。

        短于 min_chunk_size 的内容不丢弃，追加到上一个 Document。
        """
        nonlocal text_buffer, search_cursor
        if not text_buffer:
            return

        combined = "\n".join(text_buffer)
        text_buffer = []

        # 短章节：追加到前一个 Document，不独立成段（问题三修复）
        if len(combined) < min_chunk_size:
            _append_to_last(combined)
            return

        # 顺序游标定位 char_start（问题二修复）
        needle = combined[:40].split("\n")[0]  # 取第一行前40字作为锚点
        char_start = _sequential_find(full_text, needle, search_cursor)
        search_cursor = char_start + 1  # 游标向前推进，避免下次重复匹配

        if len(combined) <= chunk_size:
            chunks = [combined]
        else:
            chunks = _split_text_by_sentences(combined, chunk_size, chunk_overlap)

        offset = char_start
        for chunk_text in chunks:
            char_end = offset + len(chunk_text)
            doc = _make_doc(
                page_content=chunk_text,
                doc_id=doc_id,
                section_title=current_section_title,
                section_level=current_section_level,
                page_idx=buffer_page,
                char_start=offset,
                char_end=char_end,
                chunk_type="text",
                entity_index=entity_index,
                source=str(doc_dir),
            )
            documents.append(doc)
            offset = max(char_end - chunk_overlap, char_start)

    for block in blocks:
        block_type = block.get("type", "")
        page_idx = block.get("page_idx", 0)

        # ── 跳过不可检索块 ──
        if block_type in ("discarded", "image"):
            continue

        # ── 标题块：刷新缓冲区，更新当前 section ──
        if block_type == "text" and block.get("text_level"):
            _flush_buffer()
            current_section_title = block.get("text", "").strip()
            current_section_level = block.get("text_level", 0)
            continue

        # ── 正文块：累积到缓冲区 ──
        if block_type == "text":
            text_content = block.get("text", "").strip()
            if text_content:
                if not text_buffer:
                    buffer_page = page_idx
                text_buffer.append(text_content)
                # 超过 chunk_size 时提前刷新
                if sum(len(t) for t in text_buffer) >= chunk_size:
                    _flush_buffer()
            continue

        # ── 表格块：独立成 chunk ──
        if block_type == "table":
            _flush_buffer()  # 先刷新之前的文本
            table_body = block.get("table_body", "").strip()
            if not table_body:
                continue

            caption_raw = block.get("table_caption", [])
            caption = " ".join(caption_raw).strip() if isinstance(caption_raw, list) else str(caption_raw).strip()
            page_content = f"表格：{caption}\n{table_body}" if caption else table_body

            # 顺序游标定位（问题二修复）
            needle = table_body[:40].split("\n")[0]
            char_start = _sequential_find(full_text, needle, search_cursor)
            search_cursor = char_start + 1
            char_end = char_start + len(page_content)

            doc = _make_doc(
                page_content=page_content,
                doc_id=doc_id,
                section_title=current_section_title,
                section_level=current_section_level,
                page_idx=page_idx,
                char_start=char_start,
                char_end=char_end,
                chunk_type="table",
                entity_index=entity_index,
                source=str(doc_dir),
                table_caption=caption,
            )
            documents.append(doc)
            continue

    # 刷新剩余缓冲区
    _flush_buffer()

    return documents


def _split_plain_text(
    text: str,
    doc_id: str,
    entity_index: list[dict],
    chunk_size: int,
    chunk_overlap: int,
) -> list[Document]:
    """降级方案：对无 content_list.json 的文档（如 Excel Agent API 产物）直接切分 full.md。"""
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        add_start_index=True,
    )
    raw_chunks = splitter.create_documents([text], metadatas=[{"document_id": doc_id}])

    documents = []
    for chunk in raw_chunks:
        start = chunk.metadata.get("start_index", 0)
        end = start + len(chunk.page_content)
        entity_names, entity_types = _annotate_entities(start, end, entity_index)
        chunk.metadata.update({
            "section_title": doc_id,
            "section_level": 0,
            "page_idx": 0,
            "char_start": start,
            "char_end": end,
            "chunk_type": "text",
            "entities": json.dumps(entity_names, ensure_ascii=False),
            "entity_types": json.dumps(entity_types, ensure_ascii=False),
            "source": doc_id,
        })
        documents.append(chunk)
    return documents


# ─────────────────────────────────────────────
# 批量扫描
# ─────────────────────────────────────────────

def scan_and_split(
    mineru_output_dir: Path = config.MINERU_OUTPUT_DIR,
    doc_filter: Optional[list[str]] = None,
    chunk_size: int = config.CHUNK_SIZE,
    chunk_overlap: int = config.CHUNK_OVERLAP,
) -> list[Document]:
    """扫描 MinerU 输出目录，返回所有文档的结构感知切分结果。"""
    if not mineru_output_dir.exists():
        raise FileNotFoundError(f"MinerU 输出目录不存在：{mineru_output_dir}")

    subdirs = sorted(
        d for d in mineru_output_dir.iterdir()
        if d.is_dir() and not d.name.startswith(".")
    )
    if doc_filter:
        subdirs = [d for d in subdirs if d.name in doc_filter]

    all_docs: list[Document] = []
    for subdir in subdirs:
        docs = split_document(subdir, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        if docs:
            print(f"  [切分] {subdir.name}  → {len(docs)} chunks")
        else:
            print(f"  [跳过] {subdir.name}（无可切分内容）")
        all_docs.extend(docs)

    return all_docs
