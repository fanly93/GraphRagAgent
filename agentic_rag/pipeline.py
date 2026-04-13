"""Agentic RAG CLI 入口。

用法：
    cd agentic_rag
    source .venv/bin/activate
    python pipeline.py                         # 交互模式
    python pipeline.py "LangChain 是什么？"    # 单次提问
"""

from __future__ import annotations

import sys
import time

import config  # 必须最先导入，以便 sys.path 注入生效


def run_query(app, question: str) -> str:
    """执行单次查询，返回答案字符串。"""
    initial_state = {
        "question": question,
        "original_question": question,
        "route": "",
        "kg_results": [],
        "passage_results": [],
        "merged_context": "",
        "sufficient": False,
        "rewrite_count": 0,
        "answer": "",
    }

    print(f"\n{'='*60}")
    print(f"问题：{question}")
    print("="*60)

    t0 = time.time()
    result = app.invoke(initial_state)
    elapsed = time.time() - t0

    answer = result.get("answer", "（无答案）")
    route = result.get("route", "?")
    rewrites = result.get("rewrite_count", 0)
    kg_count = len(result.get("kg_results", []))
    passage_count = len(result.get("passage_results", []))

    print(f"\n[Pipeline] 路由={route}  KG实体={kg_count}  段落={passage_count}"
          f"  改写={rewrites}次  耗时={elapsed:.1f}s")
    print(f"\n答案：\n{answer}")
    print("="*60)

    return answer


def interactive_mode(app) -> None:
    """交互式多轮问答。"""
    print("\nAgentic RAG 交互模式（输入 'quit' 或 'exit' 退出）")
    print("-" * 60)
    while True:
        try:
            question = input("\n请输入问题：").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n已退出。")
            break
        if not question:
            continue
        if question.lower() in ("quit", "exit", "q"):
            print("已退出。")
            break
        run_query(app, question)


def main() -> None:
    # 延迟导入，避免配置未就绪时报错
    from graph import get_default_graph

    print("正在初始化 Agentic RAG 系统...")
    app = get_default_graph()
    print("初始化完成。")

    if len(sys.argv) > 1:
        # 命令行参数模式：python pipeline.py "问题"
        question = " ".join(sys.argv[1:])
        run_query(app, question)
    else:
        interactive_mode(app)


if __name__ == "__main__":
    main()
