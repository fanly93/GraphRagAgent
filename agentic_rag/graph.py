"""构建 LangGraph 5 节点 Agentic RAG 图。

图结构：
  route_question → retrieve → grade_documents → [should_rewrite] → generate_answer
                                                         ↓
                                               rewrite_question → retrieve (循环)
"""

from __future__ import annotations

from typing import Any

from langgraph.graph import StateGraph, END

from state import AgentState
from nodes.router import route_question
from nodes.retriever import retrieve
from nodes.grader import grade_documents
from nodes.rewriter import rewrite_question, should_rewrite
from nodes.generator import generate_answer
from retrievers.kg_retriever import KGRetriever
import config


def build_graph(llm: Any, kg_retriever: KGRetriever):
    """构建并编译 LangGraph 图。

    Args:
        llm: LangChain LLM 实例
        kg_retriever: KGRetriever 实例

    Returns:
        已编译的 CompiledGraph，可直接 .invoke(state) 调用
    """
    graph = StateGraph(AgentState)

    # ── 注册节点（使用偏函数注入外部依赖）────────────────────────────────
    graph.add_node("route_question", lambda s: route_question(s, llm))
    graph.add_node("retrieve", lambda s: retrieve(s, kg_retriever))
    graph.add_node("grade_documents", lambda s: grade_documents(s, llm))
    graph.add_node("rewrite_question", lambda s: rewrite_question(s, llm))
    graph.add_node("generate_answer", lambda s: generate_answer(s, llm, kg_retriever))

    # ── 设置入口节点 ──────────────────────────────────────────────────────
    graph.set_entry_point("route_question")

    # ── 固定边 ───────────────────────────────────────────────────────────
    graph.add_edge("route_question", "retrieve")
    graph.add_edge("retrieve", "grade_documents")
    graph.add_edge("rewrite_question", "retrieve")
    graph.add_edge("generate_answer", END)

    # ── 条件边：grade_documents → rewrite / generate ──────────────────────
    graph.add_conditional_edges(
        "grade_documents",
        should_rewrite,
        {
            "rewrite": "rewrite_question",
            "generate": "generate_answer",
        },
    )

    return graph.compile()


def get_default_graph():
    """使用默认配置构建图（直接可用）。"""
    from langchain_openai import ChatOpenAI

    if config.LLM_PROVIDER == "deepseek":
        llm = ChatOpenAI(
            model=config.LLM_MODEL_ID,
            api_key=config.DEEPSEEK_API_KEY,
            base_url=config.DEEPSEEK_BASE_URL,
            temperature=0,
        )
    else:  # dashscope (default)
        llm = ChatOpenAI(
            model=config.LLM_MODEL_ID,
            api_key=config.DASHSCOPE_API_KEY,
            base_url=config.DASHSCOPE_BASE_URL,
            temperature=0,
        )

    kg_retriever = KGRetriever(
        jsonl_dir=config.LANGEXTRACT_OUTPUT_DIR,
        context_window=config.KG_CONTEXT_WINDOW,
    )
    return build_graph(llm, kg_retriever)
