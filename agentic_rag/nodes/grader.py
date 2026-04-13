"""Node 3: grade_documents — 评估检索结果是否足够回答问题。"""

from __future__ import annotations

import json
import re

from state import AgentState
from prompts import GRADE_PROMPT


def grade_documents(state: AgentState, llm) -> AgentState:
    """LLM 评估 merged_context 对于 question 的充分性。

    输出 state 字段：sufficient
    """
    question = state["question"]
    context = state.get("merged_context", "")
    route = state.get("route", "")

    # 直接回答模式跳过评估
    if route == "direct_answer" or not context:
        return {**state, "sufficient": True}

    # 截断上下文避免 prompt 过长
    context_preview = context[:2000] if len(context) > 2000 else context
    prompt = GRADE_PROMPT.format(question=question, context=context_preview)

    response = llm.invoke(prompt)
    raw = response.content.strip()

    # 解析 JSON，容错处理
    sufficient = True
    reason = ""
    try:
        # 提取 JSON 块（可能有多余文字）
        match = re.search(r'\{.*?\}', raw, re.DOTALL)
        if match:
            data = json.loads(match.group())
            sufficient = bool(data.get("sufficient", True))
            reason = data.get("reason", "")
    except Exception:
        # 解析失败则视为充分（避免死循环）
        sufficient = True

    status = "充分 ✅" if sufficient else f"不足 ⚠️  {reason}"
    print(f"  [Grader] {status}")

    return {**state, "sufficient": sufficient, "_grade_reason": reason}
