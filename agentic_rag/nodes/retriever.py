"""Node 2: retrieve — 按路由策略执行检索。

三种工具：
  - kg_retrieve：KG 实体检索（精确属性查询）
  - passage_retrieve：Hybrid 向量+BM25 段落检索
  - fusion_retrieve：两路并行（复杂问题）
"""

from __future__ import annotations

from state import AgentState
from retrievers.kg_retriever import KGRetriever
from retrievers.hybrid_retriever import retrieve_passages, format_passages_for_prompt
import config


def retrieve(state: AgentState, kg_retriever: KGRetriever) -> AgentState:
    """根据 state.route 选择检索策略，填充 kg_results / passage_results / merged_context。"""
    question = state["question"]
    route = state.get("route", "hybrid_query")

    kg_results: list[dict] = []
    passage_results = []

    print(f"  [Retriever] 策略={route}  问题={question[:40]}...")

    if route in ("entity_query", "hybrid_query"):
        kg_results = kg_retriever.retrieve(question, top_k=config.KG_TOP_K)
        print(f"  [Retriever] KG 召回 {len(kg_results)} 个实体")

    if route in ("semantic_query", "hybrid_query"):
        passage_results = retrieve_passages(question, top_k=config.RETRIEVAL_TOP_K)
        print(f"  [Retriever] 段落召回 {len(passage_results)} 个 chunks")

    if route == "direct_answer":
        # 直接回答，跳过检索
        return {**state, "kg_results": [], "passage_results": [], "merged_context": ""}

    # 格式化合并上下文
    kg_context = kg_retriever.format_for_prompt(kg_results)
    passage_context = format_passages_for_prompt(passage_results)
    merged = f"=== 知识图谱实体 ===\n{kg_context}\n\n=== 文档段落 ===\n{passage_context}"

    return {
        **state,
        "kg_results": kg_results,
        "passage_results": passage_results,
        "merged_context": merged,
    }
