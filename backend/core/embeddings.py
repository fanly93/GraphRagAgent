"""Embedding 模型创建。"""

from __future__ import annotations
import sys
sys.path.insert(0, str(__import__('pathlib').Path(__file__).parent.parent))

import config


def create_embeddings():
    """创建 Embedding 实例（DashScope 或 OpenAI 兼容接口）。"""
    from langchain_openai import OpenAIEmbeddings
    return OpenAIEmbeddings(
        model=config.DASHSCOPE_EMBEDDING_MODEL,
        openai_api_key=config.DASHSCOPE_API_KEY,
        openai_api_base=config.DASHSCOPE_BASE_URL,
        # DashScope 仅接受原始字符串，不支持 tiktoken 批量 token 输入
        check_embedding_ctx_length=False,
        # DashScope 单批最多 10 条
        chunk_size=10,
    )
