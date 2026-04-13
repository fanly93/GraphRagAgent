"""LangGraph State 定义。"""

from __future__ import annotations

from typing import Annotated, Any
from typing_extensions import TypedDict

from langchain_core.documents import Document
from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    """Agentic RAG 全局状态，在各节点间流转。"""

    # ── 输入 ──
    question: str                         # 原始用户问题
    original_question: str                # 保留原始问题（改写后对比用）

    # ── 路由 ──
    route: str                            # entity_query | semantic_query | hybrid_query | direct_answer

    # ── 检索结果 ──
    kg_results: list[dict]                # KG 实体卡片列表
    passage_results: list[Document]       # 向量+BM25 段落列表
    merged_context: str                   # 格式化后的合并上下文（供 grade/generate 使用）

    # ── 评估 ──
    sufficient: bool                      # 当前检索是否足够回答问题
    rewrite_count: int                    # 已改写次数

    # ── 输出 ──
    answer: str                           # 最终答案
