"""Node 4: rewrite_question — 检索不足时改写问题重试。"""

from __future__ import annotations

from state import AgentState
from prompts import REWRITE_PROMPT
import config


def rewrite_question(state: AgentState, llm) -> AgentState:
    """改写问题以提升检索效果，并递增 rewrite_count。

    输出 state 字段：question（改写后）、rewrite_count
    """
    question = state["question"]
    reason = state.get("_grade_reason", "检索结果与问题相关性不足")
    count = state.get("rewrite_count", 0)

    prompt = REWRITE_PROMPT.format(question=question, reason=reason)
    response = llm.invoke(prompt)
    new_question = response.content.strip()

    print(f"  [Rewriter] 第 {count + 1} 次改写")
    print(f"    原问题：{question}")
    print(f"    新问题：{new_question}")

    return {
        **state,
        "question": new_question,
        "rewrite_count": count + 1,
    }


def should_rewrite(state: AgentState) -> str:
    """条件边：判断是否继续改写或直接生成答案。

    Returns:
        "rewrite"：继续改写
        "generate"：直接生成（充分 or 超过最大改写次数）
    """
    if state.get("sufficient", True):
        return "generate"
    if state.get("rewrite_count", 0) >= config.MAX_REWRITE_ATTEMPTS:
        print(f"  [Rewriter] 已达最大改写次数 {config.MAX_REWRITE_ATTEMPTS}，强制生成")
        return "generate"
    return "rewrite"
