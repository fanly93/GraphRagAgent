"""Node 5: generate_answer — 基于融合上下文生成最终答案。"""

from __future__ import annotations

from state import AgentState
from prompts import GENERATE_PROMPT, DIRECT_ANSWER_PROMPT
from retrievers.hybrid_retriever import format_passages_for_prompt
from retrievers.kg_retriever import KGRetriever


def generate_answer(state: AgentState, llm, kg_retriever: KGRetriever) -> AgentState:
    """生成最终答案，引用 KG 实体和段落来源。

    输出 state 字段：answer
    """
    question = state["question"]
    route = state.get("route", "hybrid_query")

    # 直接回答（无检索）
    if route == "direct_answer":
        prompt = DIRECT_ANSWER_PROMPT.format(question=question)
        response = llm.invoke(prompt)
        return {**state, "answer": response.content.strip()}

    # 构建分段上下文
    kg_results = state.get("kg_results", [])
    passage_results = state.get("passage_results", [])

    kg_context = kg_retriever.format_for_prompt(kg_results) if kg_results else "（未检索实体信息）"
    passage_context = format_passages_for_prompt(passage_results) if passage_results else "（未检索段落信息）"

    prompt = GENERATE_PROMPT.format(
        kg_context=kg_context,
        passage_context=passage_context,
        question=question,
    )

    print(f"  [Generator] 生成答案（KG={len(kg_results)}实体, 段落={len(passage_results)}块）")
    response = llm.invoke(prompt)
    answer = response.content.strip()

    return {**state, "answer": answer}
