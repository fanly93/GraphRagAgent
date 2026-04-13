"""KG 实体检索器（BM25 over JSONL）。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
import config


class KGRetriever:
    """基于 JSONL 的 KG 实体检索器，使用 BM25 进行关键词匹配。"""

    def __init__(
        self,
        kg_output_dir: Path = config.KG_OUTPUT_DIR,
        context_window: int = config.KG_CONTEXT_WINDOW,
        doc_ids: Optional[list[str]] = None,  # None = 全库
    ):
        self.kg_output_dir = kg_output_dir
        self.context_window = context_window
        self.doc_ids = set(doc_ids) if doc_ids else None
        self._entities: list[dict] = []
        self._corpus: list[str] = []
        self._bm25 = None
        self._load()

    def _load(self) -> None:
        if not self.kg_output_dir.exists():
            print(f"  [KG] 目录不存在：{self.kg_output_dir}")
            return

        for f in sorted(self.kg_output_dir.glob("*.jsonl")):
            try:
                with open(f, encoding="utf-8") as fp:
                    for line in fp:
                        line = line.strip()
                        if not line:
                            continue
                        doc = json.loads(line)
                        doc_id = doc.get("document_id", "")
                        if self.doc_ids and doc_id not in self.doc_ids:
                            continue
                        self._index_document(doc)
            except Exception as e:
                print(f"  [KG] 跳过 {f.name}：{e}")

        self._build_bm25()
        print(f"  [KG] 已加载 {len(self._entities)} 个实体")

    def _index_document(self, doc: dict) -> None:
        doc_id = doc.get("document_id", "unknown")
        full_text = doc.get("text", "")
        for e in doc.get("extractions", []):
            ci = e.get("char_interval")
            if not ci or e.get("alignment_status") != "match_exact":
                continue
            s = max(0, ci["start_pos"] - self.context_window)
            end = min(len(full_text), ci["end_pos"] + self.context_window)
            context_snippet = full_text[s:end].strip()
            attrs = e.get("attributes") or {}
            if not isinstance(attrs, dict):
                attrs = {}
            record = {
                "entity_text": e.get("extraction_text", ""),
                "entity_class": e.get("extraction_class", ""),
                "attributes": attrs,
                "document_id": doc_id,
                "char_start": ci["start_pos"],
                "char_end": ci["end_pos"],
                "context_snippet": context_snippet,
            }
            self._entities.append(record)
            attr_vals = " ".join(str(v) for v in attrs.values())
            self._corpus.append(f"{record['entity_text']} {attr_vals}")

    def _build_bm25(self) -> None:
        if not self._corpus:
            return
        try:
            from rank_bm25 import BM25Okapi
            tokenized = [text.split() for text in self._corpus]
            self._bm25 = BM25Okapi(tokenized)
        except ImportError:
            print("  [KG] rank_bm25 未安装，使用子串匹配")

    def retrieve(self, query: str, top_k: int = config.KG_TOP_K) -> list[dict]:
        if not self._entities:
            return []
        if self._bm25 is not None:
            scores = self._bm25.get_scores(query.split())
            ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)
            results = []
            for idx, score in ranked[:top_k]:
                if score <= 0:
                    break
                record = dict(self._entities[idx])
                record["score"] = float(score)
                results.append(record)
            return results

        # fallback 子串匹配
        query_lower = query.lower()
        matched = []
        for entity in self._entities:
            text = f"{entity['entity_text']} {' '.join(str(v) for v in entity['attributes'].values())}".lower()
            if any(kw in text for kw in query_lower.split()):
                matched.append({**entity, "score": 1.0})
        return matched[:top_k]

    def format_for_prompt(self, results: list[dict]) -> str:
        if not results:
            return "（无相关实体信息）"
        parts = []
        for i, r in enumerate(results, 1):
            attrs = "\n".join(f"    {k}: {v}" for k, v in r["attributes"].items()) if r["attributes"] else "    （无属性）"
            snippet = r["context_snippet"][:300].replace("\n", " ")
            part = (
                f"[实体 {i}] {r['entity_text']}（{r['entity_class']}）\n"
                f"  来源文档：{r['document_id']}\n"
                f"  属性：\n{attrs}\n"
                f"  原文上下文：...{snippet}..."
            )
            parts.append(part)
        return "\n\n".join(parts)

    @property
    def entity_count(self) -> int:
        return len(self._entities)
