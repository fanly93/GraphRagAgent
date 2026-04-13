"""KG 实体检索器。

从 LangExtract JSONL 文件加载实体索引，
使用 BM25 对 entity_text + attributes 做关键词检索，
并从原文中提取实体周围的上下文窗口。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import config


class KGRetriever:
    """基于 LangExtract 抽取结果的实体级检索器。

    检索粒度：实体（平均 54.5 字），附带 attributes KV 和原文上下文窗口。
    适合：属性查询、关系追踪、精确事实核查。
    """

    def __init__(
        self,
        jsonl_dir: Path = config.LANGEXTRACT_OUTPUT_DIR,
        context_window: int = config.KG_CONTEXT_WINDOW,
        min_alignment: str = "match_exact",  # match_exact | match_fuzzy
    ):
        self.context_window = context_window
        self.min_alignment = min_alignment
        self._entities: list[dict] = []   # 完整实体列表
        self._corpus: list[str] = []      # BM25 检索文本（entity_text + attr values）
        self._bm25 = None
        self._load(jsonl_dir)

    # ─────────────────────────────────────────────
    # 加载
    # ─────────────────────────────────────────────

    def _load(self, jsonl_dir: Path) -> None:
        """扫描 JSONL 目录，加载所有 grounded 实体。"""
        if not jsonl_dir.exists():
            print(f"  [KG] 目录不存在：{jsonl_dir}")
            return

        loaded_docs = 0
        for f in sorted(jsonl_dir.glob("*.jsonl")):
            try:
                with open(f, encoding="utf-8") as fp:
                    content = fp.read().strip()
                # 支持单行 JSON 或 JSONL 多行
                lines = [l for l in content.splitlines() if l.strip()]
                for line in lines:
                    doc = json.loads(line)
                    self._index_document(doc)
                    loaded_docs += 1
            except Exception as e:
                print(f"  [KG] 跳过 {f.name}：{e}")

        self._build_bm25()
        print(f"  [KG] 已加载 {loaded_docs} 个文档，{len(self._entities)} 个实体")

    def _index_document(self, doc: dict) -> None:
        """将单个 AnnotatedDocument 中的 grounded 实体加入索引。"""
        doc_id = doc.get("document_id", "unknown")
        full_text = doc.get("text", "")

        accept_statuses = {"match_exact"}
        if self.min_alignment == "match_fuzzy":
            accept_statuses.add("match_fuzzy")

        for e in doc.get("extractions", []):
            ci = e.get("char_interval")
            status = e.get("alignment_status")
            if not ci or status not in accept_statuses:
                continue

            # 提取原文上下文窗口
            s = max(0, ci["start_pos"] - self.context_window)
            end = min(len(full_text), ci["end_pos"] + self.context_window)
            context_snippet = full_text[s:end].strip()

            entity_record = {
                "entity_text": e.get("extraction_text", ""),
                "entity_class": e.get("extraction_class", ""),
                "attributes": e.get("attributes") or {},
                "document_id": doc_id,
                "char_start": ci["start_pos"],
                "char_end": ci["end_pos"],
                "alignment_status": status,
                "context_snippet": context_snippet,
            }
            self._entities.append(entity_record)

            # BM25 检索文本 = entity_text + 所有 attribute values 拼接
            attr_vals = " ".join(str(v) for v in entity_record["attributes"].values())
            self._corpus.append(f"{entity_record['entity_text']} {attr_vals}")

    def _build_bm25(self) -> None:
        """构建 BM25 索引。"""
        if not self._corpus:
            return
        try:
            from rank_bm25 import BM25Okapi
            tokenized = [text.split() for text in self._corpus]
            self._bm25 = BM25Okapi(tokenized)
        except ImportError:
            print("  [KG] rank_bm25 未安装，降级为关键词子串匹配")

    # ─────────────────────────────────────────────
    # 检索
    # ─────────────────────────────────────────────

    def retrieve(self, query: str, top_k: int = config.KG_TOP_K) -> list[dict]:
        """检索与 query 最相关的实体卡片。

        Returns:
            list[dict]，每项包含 entity_text / entity_class / attributes /
            document_id / context_snippet / score
        """
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

        # fallback：子串匹配
        query_lower = query.lower()
        matched = []
        for entity in self._entities:
            text = f"{entity['entity_text']} {' '.join(str(v) for v in entity['attributes'].values())}".lower()
            if any(kw in text for kw in query_lower.split()):
                matched.append({**entity, "score": 1.0})
        return matched[:top_k]

    def format_for_prompt(self, results: list[dict]) -> str:
        """将实体检索结果格式化为 Prompt 上下文字符串。"""
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
