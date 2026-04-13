"""Node 1: route_question — 判断问题类型，决定检索策略。"""

from __future__ import annotations

from state import AgentState
from prompts import ROUTE_PROMPT


VALID_ROUTES = {"entity_query", "semantic_query", "hybrid_query", "direct_answer"}


def route_question(state: AgentState, llm) -> AgentState:
    """根据问题内容路由到对应检索策略。

    输出 state 字段：route
    """
    question = state["question"]
    prompt = ROUTE_PROMPT.format(question=question)

    response = llm.invoke(prompt)
    route = response.content.strip().lower()

    # 容错：若输出不在合法值中，默认用 hybrid_query
    if route not in VALID_ROUTES:
        print(f"  [Router] 未识别路由 '{route}'，回退到 hybrid_query")
        route = "hybrid_query"

    print(f"  [Router] 问题类型 → {route}")
    return {
        **state,
        "route": route,
        "original_question": question,
        "rewrite_count": state.get("rewrite_count", 0),
    }
