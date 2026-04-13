"""KG 实体抽取：从 MinerU 解析结果中抽取命名实体，写入 JSONL。"""

from __future__ import annotations

import json
import re
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
import config
from core.prompts import KG_EXTRACT_PROMPT


def _find_char_interval(text: str, entity_text: str, cursor: int = 0) -> Optional[dict]:
    """在 text 中从 cursor 开始查找 entity_text，返回 char_interval 或 None。"""
    pos = text.find(entity_text, cursor)
    if pos == -1:
        # 宽松匹配：忽略大小写
        lower_text = text.lower()
        lower_entity = entity_text.lower()
        pos = lower_text.find(lower_entity, cursor)
        if pos == -1:
            return None
    return {"start_pos": pos, "end_pos": pos + len(entity_text)}


def extract_entities_from_text(text: str, llm) -> list[dict]:
    """用 LLM 从文本中抽取实体列表。"""
    if not text or len(text.strip()) < 20:
        return []

    prompt = KG_EXTRACT_PROMPT.format(text=text[:3000])  # 截断防止超长
    try:
        response = llm.invoke(prompt)
        raw = response.content.strip()

        # 提取 JSON 数组
        match = re.search(r'\[.*?\]', raw, re.DOTALL)
        if not match:
            return []

        entities = json.loads(match.group())
        if not isinstance(entities, list):
            return []
        return entities
    except Exception as e:
        print(f"  [KG Extract] 抽取失败：{e}")
        return []


def build_kg_index(
    doc_id: str,
    mineru_output_dir: Path,
    kg_output_dir: Path,
    llm,
) -> int:
    """
    从 MinerU 输出构建 KG JSONL。
    返回抽取的 match_exact 实体数量。
    """
    doc_dir = mineru_output_dir / doc_id
    content_list_path = doc_dir / "content_list.json"
    full_md_path = doc_dir / "full.md"

    # 读取原始文本
    full_text = ""
    if content_list_path.exists():
        with open(content_list_path, encoding="utf-8") as f:
            items = json.load(f)
        full_text = "\n".join(
            item.get("text", "")
            for item in items
            if item.get("type") in ("text", "title") and item.get("text", "").strip()
        )
    elif full_md_path.exists():
        with open(full_md_path, encoding="utf-8") as f:
            full_text = f.read()

    if not full_text.strip():
        print(f"  [KG] doc_id={doc_id} 无可抽取文本")
        return 0

    print(f"  [KG] 开始抽取 doc_id={doc_id}，文本长度={len(full_text)}")

    # 分段抽取（每段 2000 字，避免超长 prompt）
    segment_size = 2000
    all_raw_entities: list[dict] = []
    for start in range(0, len(full_text), segment_size):
        segment = full_text[start: start + segment_size]
        raw_entities = extract_entities_from_text(segment, llm)
        all_raw_entities.extend(raw_entities)

    print(f"  [KG] 抽取原始实体 {len(all_raw_entities)} 个")

    # 去重（按 entity_text 去重，保留第一个）
    seen: set[str] = set()
    unique_entities: list[dict] = []
    for e in all_raw_entities:
        name = e.get("entity_text", "").strip()
        if name and name not in seen:
            seen.add(name)
            unique_entities.append(e)

    # 将 entity_text 与原文对齐，生成 char_interval + alignment_status
    extractions = []
    for e in unique_entities:
        entity_text = e.get("entity_text", "").strip()
        entity_class = e.get("entity_class", "other")
        attributes = e.get("attributes", {})
        if not isinstance(attributes, dict):
            attributes = {}
        # 确保 attributes 值全为字符串
        attributes = {str(k): str(v) for k, v in attributes.items()}

        ci = _find_char_interval(full_text, entity_text)
        if ci:
            alignment_status = "match_exact"
        else:
            ci = {"start_pos": 0, "end_pos": len(entity_text)}
            alignment_status = "not_grounded"

        extractions.append({
            "extraction_text": entity_text,
            "extraction_class": entity_class,
            "attributes": attributes,
            "char_interval": ci,
            "alignment_status": alignment_status,
        })

    match_exact_count = sum(1 for e in extractions if e["alignment_status"] == "match_exact")
    print(f"  [KG] match_exact 实体：{match_exact_count} / {len(extractions)}")

    # 构建 AnnotatedDocument 结构并写入 JSONL
    annotated_doc = {
        "document_id": doc_id,
        "text": full_text,
        "extractions": extractions,
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    kg_output_dir.mkdir(parents=True, exist_ok=True)
    output_path = kg_output_dir / f"{doc_id}.jsonl"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(json.dumps(annotated_doc, ensure_ascii=False) + "\n")

    print(f"  [KG] 已写入 {output_path}")
    return match_exact_count


def delete_kg_file(doc_id: str, kg_output_dir: Path) -> None:
    """删除指定 doc_id 的 KG JSONL 文件。"""
    target = kg_output_dir / f"{doc_id}.jsonl"
    if target.exists():
        target.unlink()
        print(f"  [KG] 已删除 {target}")
