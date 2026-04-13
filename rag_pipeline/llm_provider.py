"""LLM 工厂（RAG 生成阶段）。

复用 langextract_pipeline 的 OpenAI-compatible 接入方式，
支持 DashScope / DeepSeek。
"""

import config
from langchain_openai import ChatOpenAI


def create_llm() -> ChatOpenAI:
    """根据 LLM_PROVIDER 配置创建 ChatOpenAI 实例。"""
    provider = config.LLM_PROVIDER.lower()

    if provider == "dashscope":
        if not config.DASHSCOPE_API_KEY:
            raise ValueError("DASHSCOPE_API_KEY 未配置")
        print(f"  [LLM] DashScope  model={config.LLM_MODEL_ID}")
        return ChatOpenAI(
            model=config.LLM_MODEL_ID,
            api_key=config.DASHSCOPE_API_KEY,
            base_url=config.DASHSCOPE_BASE_URL,
            temperature=0.1,
        )

    if provider == "deepseek":
        if not config.DEEPSEEK_API_KEY:
            raise ValueError("DEEPSEEK_API_KEY 未配置")
        print(f"  [LLM] DeepSeek  model={config.LLM_MODEL_ID}")
        return ChatOpenAI(
            model=config.LLM_MODEL_ID,
            api_key=config.DEEPSEEK_API_KEY,
            base_url=config.DEEPSEEK_BASE_URL,
            temperature=0.1,
        )

    raise ValueError(f"未知 LLM_PROVIDER='{provider}'，支持：dashscope | deepseek")
