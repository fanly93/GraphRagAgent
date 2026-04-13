"""基于 MinerU content_list.json 的结构感知文档切分器。"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

from langchain_core.documents import Document

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
import config


def _split_text(text: str, chunk_size: int, chunk_overlap: int) -> list[str]:
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
    return chunks or [text]


def _load_entity_index(doc_id: str, kg_output_dir: Path) -> list[dict]:
    for f in sorted(kg_output_dir.glob("*.jsonl")):
        try:
            with open(f, encoding="utf-8") as fp:
                for line in fp:
                    line = line.strip()
                    if not line:
                        continue
                    doc = json.loads(line)
                    if doc.get("document_id") == doc_id:
                        return [
                            e for e in doc.get("extractions", [])
                            if e.get("char_interval") and e.get("alignment_status") == "match_exact"
                        ]
        except Exception:
            pass
    return []


def _annotate_entities(char_start: int, char_end: int, entity_index: list[dict]):
    names, types = [], []
    for e in entity_index:
        ci = e["char_interval"]
        if ci["start_pos"] >= char_start and ci["end_pos"] <= char_end:
            names.append(e["extraction_text"])
            types.append(e["extraction_class"])
    return names, types


def split_document(
    doc_id: str,
    mineru_output_dir: Path,
    kg_output_dir: Path,
    chunk_size: int = config.CHUNK_SIZE,
    chunk_overlap: int = config.CHUNK_OVERLAP,
) -> list[Document]:
    """从 MinerU 输出目录切分文档，返回 Document 列表。"""
    doc_dir = mineru_output_dir / doc_id
    content_list_path = doc_dir / "content_list.json"
    full_md_path = doc_dir / "full.md"

    # 优先使用 content_list.json（结构感知）
    if content_list_path.exists():
        return _split_from_content_list(doc_id, content_list_path, kg_output_dir, chunk_size, chunk_overlap)

    # fallback: 直接切分 full.md
    if full_md_path.exists():
        return _split_from_markdown(doc_id, full_md_path, chunk_size, chunk_overlap)

    return []


def _split_from_content_list(
    doc_id: str,
    content_list_path: Path,
    kg_output_dir: Path,
    chunk_size: int,
    chunk_overlap: int,
) -> list[Document]:
    with open(content_list_path, encoding="utf-8") as f:
        items = json.load(f)

    entity_index = _load_entity_index(doc_id, kg_output_dir)
    full_text = " ".join(
        item.get("text", "") for item in items
        if item.get("type") in ("text", "title")
    )

    documents: list[Document] = []
    current_section = "Introduction"
    current_level = 1
    current_page = 0
    buffer: list[str] = []
    buffer_char_start = 0
    char_cursor = 0

    def flush_buffer():
        nonlocal char_cursor
        if not buffer:
            return
        combined = " ".join(buffer)
        if len(combined) < 30:
            return
        chunks = _split_text(combined, chunk_size, chunk_overlap)
        for chunk_text in chunks:
            pos = full_text.find(chunk_text[:50], max(0, char_cursor - 100))
            c_start = pos if pos != -1 else char_cursor
            c_end = c_start + len(chunk_text)
            names, types = _annotate_entities(c_start, c_end, entity_index)
            documents.append(Document(
                page_content=chunk_text,
                metadata={
                    "document_id": doc_id,
                    "section_title": current_section,
                    "section_level": current_level,
                    "page_idx": current_page,
                    "char_start": c_start,
                    "char_end": c_end,
                    "chunk_type": "text",
                    "entities": json.dumps(names, ensure_ascii=False),
                    "entity_types": json.dumps(types, ensure_ascii=False),
                },
            ))
        buffer.clear()

    for item in items:
        item_type = item.get("type", "")
        text = item.get("text", "").strip()
        page_idx = item.get("page_idx", 0)
        current_page = page_idx

        if item_type == "title":
            flush_buffer()
            level = item.get("text_level", 1)
            current_section = text
            current_level = level
            buffer_char_start = char_cursor

        elif item_type == "text" and text:
            buffer.append(text)
            char_cursor += len(text) + 1

        elif item_type == "table":
            flush_buffer()
            caption = item.get("table_caption", "")
            table_body = item.get("table_body", "") or item.get("text", "")
            if table_body:
                content = f"{caption}\n{table_body}".strip() if caption else table_body
                pos = full_text.find(content[:40], max(0, char_cursor - 50)) if content else -1
                c_start = pos if pos != -1 else char_cursor
                c_end = c_start + len(content)
                documents.append(Document(
                    page_content=content,
                    metadata={
                        "document_id": doc_id,
                        "section_title": current_section,
                        "section_level": current_level,
                        "page_idx": page_idx,
                        "char_start": c_start,
                        "char_end": c_end,
                        "chunk_type": "table",
                        "entities": "[]",
                        "entity_types": "[]",
                    },
                ))
                char_cursor = c_end + 1

    flush_buffer()
    return documents


def _split_from_markdown(
    doc_id: str,
    full_md_path: Path,
    chunk_size: int,
    chunk_overlap: int,
) -> list[Document]:
    with open(full_md_path, encoding="utf-8") as f:
        content = f.read()

    chunks = _split_text(content, chunk_size, chunk_overlap)
    documents = []
    char_cursor = 0
    for i, chunk in enumerate(chunks):
        c_start = content.find(chunk[:40], char_cursor)
        c_start = c_start if c_start != -1 else char_cursor
        c_end = c_start + len(chunk)
        documents.append(Document(
            page_content=chunk,
            metadata={
                "document_id": doc_id,
                "section_title": f"Section {i+1}",
                "section_level": 1,
                "page_idx": 0,
                "char_start": c_start,
                "char_end": c_end,
                "chunk_type": "text",
                "entities": "[]",
                "entity_types": "[]",
            },
        ))
        char_cursor = c_end
    return documents
