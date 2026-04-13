"""LangGraph 5 节点 Agentic RAG 图。"""

from __future__ import annotations

import json
import re
import time
from typing import TypedDict, Optional

from langchain_openai import ChatOpenAI

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
import config
from core.prompts import (
    ROUTE_PROMPT, GRADE_PROMPT, REWRITE_PROMPT,
    GENERATE_PROMPT, DIRECT_ANSWER_PROMPT
)
from core.kg_retriever import KGRetriever
from core.hybrid_retriever import retrieve_passages, format_passages_for_prompt


# ── State ─────────────────────────────────────────────────────────

class AgentState(TypedDict):
    question: str
    original_question: str
    route: str
    kg_results: list[dict]
    passage_results: list
    merged_context: str
    sufficient: bool
    rewrite_count: int
    answer: str
    _grade_reason: Optional[str]
    doc_ids: Optional[list[str]]


VALID_ROUTES = {"entity_query", "semantic_query", "hybrid_query", "direct_answer"}


# ── Nodes ─────────────────────────────────────────────────────────

def node_route_question(state: AgentState, llm) -> AgentState:
    question = state["question"]
    prompt = ROUTE_PROMPT.format(question=question)
    response = llm.invoke(prompt)
    route = response.content.strip().lower()
    if route not in VALID_ROUTES:
        route = "hybrid_query"
    print(f"  [Router] → {route}")
    return {**state, "route": route, "original_question": question, "rewrite_count": state.get("rewrite_count", 0)}


def node_retrieve(state: AgentState, kg_retriever: KGRetriever) -> AgentState:
    question = state["question"]
    route = state.get("route", "hybrid_query")
    doc_ids = state.get("doc_ids")
    kg_results: list[dict] = []
    passage_results = []

    if route in ("entity_query", "hybrid_query"):
        kg_results = kg_retriever.retrieve(question, top_k=config.KG_TOP_K)
        print(f"  [Retriever] KG 召回 {len(kg_results)} 个实体")

    if route in ("semantic_query", "hybrid_query"):
        try:
            passage_results = retrieve_passages(question, top_k=config.RETRIEVAL_TOP_K, doc_ids=doc_ids)
            print(f"  [Retriever] 段落召回 {len(passage_results)} 个 chunks")
        except Exception as e:
            print(f"  [Retriever] 段落检索失败：{e}")

    if route == "direct_answer":
        return {**state, "kg_results": [], "passage_results": [], "merged_context": ""}

    kg_context = kg_retriever.format_for_prompt(kg_results)
    passage_context = format_passages_for_prompt(passage_results)
    merged = f"=== 知识图谱实体 ===\n{kg_context}\n\n=== 文档段落 ===\n{passage_context}"

    return {**state, "kg_results": kg_results, "passage_results": passage_results, "merged_context": merged}


def node_grade_documents(state: AgentState, llm) -> AgentState:
    question = state["question"]
    context = state.get("merged_context", "")
    route = state.get("route", "")

    if route == "direct_answer" or not context:
        return {**state, "sufficient": True}

    context_preview = context[:2000]
    prompt = GRADE_PROMPT.format(question=question, context=context_preview)
    response = llm.invoke(prompt)
    raw = response.content.strip()

    sufficient = True
    reason = ""
    try:
        match = re.search(r'\{.*?\}', raw, re.DOTALL)
        if match:
            data = json.loads(match.group())
            sufficient = bool(data.get("sufficient", True))
            reason = data.get("reason", "")
    except Exception:
        sufficient = True

    print(f"  [Grader] {'充分 ✅' if sufficient else f'不足 ⚠️  {reason}'}")
    return {**state, "sufficient": sufficient, "_grade_reason": reason}


def node_rewrite_question(state: AgentState, llm) -> AgentState:
    question = state["question"]
    reason = state.get("_grade_reason", "检索结果相关性不足")
    count = state.get("rewrite_count", 0)
    prompt = REWRITE_PROMPT.format(question=question, reason=reason)
    response = llm.invoke(prompt)
    new_question = response.content.strip()
    print(f"  [Rewriter] 第{count+1}次改写: {question[:30]} → {new_question[:30]}")
    return {**state, "question": new_question, "rewrite_count": count + 1}


def node_generate_answer(state: AgentState, llm, kg_retriever: KGRetriever) -> AgentState:
    question = state["question"]
    route = state.get("route", "hybrid_query")

    if route == "direct_answer":
        prompt = DIRECT_ANSWER_PROMPT.format(question=question)
        response = llm.invoke(prompt)
        return {**state, "answer": response.content.strip()}

    kg_results = state.get("kg_results", [])
    passage_results = state.get("passage_results", [])
    kg_context = kg_retriever.format_for_prompt(kg_results) if kg_results else "（未检索实体信息）"
    passage_context = format_passages_for_prompt(passage_results) if passage_results else "（未检索段落信息）"

    prompt = GENERATE_PROMPT.format(kg_context=kg_context, passage_context=passage_context, question=question)
    print(f"  [Generator] 生成答案（KG={len(kg_results)}, 段落={len(passage_results)}）")
    response = llm.invoke(prompt)
    return {**state, "answer": response.content.strip()}


def _should_rewrite(state: AgentState) -> str:
    if state.get("sufficient", True):
        return "generate"
    if state.get("rewrite_count", 0) >= config.MAX_REWRITE_ATTEMPTS:
        print(f"  [Rewriter] 已达最大改写次数 {config.MAX_REWRITE_ATTEMPTS}")
        return "generate"
    return "rewrite"


# ── Graph 构建 ────────────────────────────────────────────────────

def _create_llm() -> ChatOpenAI:
    if config.LLM_PROVIDER == "deepseek":
        return ChatOpenAI(
            model=config.LLM_MODEL_ID,
            api_key=config.DEEPSEEK_API_KEY,
            base_url=config.DEEPSEEK_BASE_URL,
        )
    # DashScope qwen3 系列默认开启 thinking 模式，需显式关闭以保证速度
    extra_body = {}
    if "qwen3" in config.LLM_MODEL_ID.lower():
        extra_body = {"enable_thinking": False}
    return ChatOpenAI(
        model=config.LLM_MODEL_ID,
        api_key=config.DASHSCOPE_API_KEY,
        base_url=config.DASHSCOPE_BASE_URL,
        model_kwargs={"extra_body": extra_body} if extra_body else {},
    )


def build_graph(doc_ids: list[str] | None = None):
    """构建并编译 LangGraph，返回可调用的 app。"""
    from langgraph.graph import StateGraph, END

    llm = _create_llm()
    kg_retriever = KGRetriever(doc_ids=doc_ids)

    graph = StateGraph(AgentState)
    graph.add_node("route_question", lambda s: node_route_question(s, llm))
    graph.add_node("retrieve", lambda s: node_retrieve(s, kg_retriever))
    graph.add_node("grade_documents", lambda s: node_grade_documents(s, llm))
    graph.add_node("rewrite_question", lambda s: node_rewrite_question(s, llm))
    graph.add_node("generate_answer", lambda s: node_generate_answer(s, llm, kg_retriever))

    graph.set_entry_point("route_question")
    graph.add_edge("route_question", "retrieve")
    graph.add_edge("retrieve", "grade_documents")
    graph.add_edge("rewrite_question", "retrieve")
    graph.add_edge("generate_answer", END)
    graph.add_conditional_edges(
        "grade_documents",
        _should_rewrite,
        {"rewrite": "rewrite_question", "generate": "generate_answer"},
    )

    return graph.compile()


# ── 全局单例 ──────────────────────────────────────────────────────
_default_app = None


def get_default_graph():
    global _default_app
    if _default_app is None:
        print("  [RAGGraph] 首次加载，构建图...")
        _default_app = build_graph()
    return _default_app


def reset_graph():
    """重置单例（索引更新后调用）。"""
    global _default_app
    _default_app = None
