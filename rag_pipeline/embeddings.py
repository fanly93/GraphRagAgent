"""Embedding 模型工厂。

支持：
  - DashScope text-embedding-v3（OpenAI-compatible，推荐，中文优化）
  - OpenAI text-embedding-3-large（备选）

后续扩展（LlamaIndex）：
  可在此添加 LlamaIndex embedding 工厂函数，对外接口保持统一。
"""

import config
from langchain_openai import OpenAIEmbeddings


def create_embeddings() -> OpenAIEmbeddings:
    """根据 EMBEDDING_PROVIDER 创建 Embeddings 实例。

    Returns:
        LangChain Embeddings 实例（兼容 Chroma / FAISS 等向量库）
    """
    provider = config.EMBEDDING_PROVIDER.lower()

    if provider == "dashscope":
        if not config.DASHSCOPE_API_KEY:
            raise ValueError("DASHSCOPE_API_KEY 未配置")
        print(f"  [Embedding] DashScope  model={config.DASHSCOPE_EMBEDDING_MODEL}")
        return OpenAIEmbeddings(
            model=config.DASHSCOPE_EMBEDDING_MODEL,
            api_key=config.DASHSCOPE_API_KEY,
            base_url=config.DASHSCOPE_BASE_URL,
            # DashScope 仅接受原始字符串，不支持 token 批量输入
            check_embedding_ctx_length=False,
            # DashScope 单批最多 10 条
            chunk_size=10,
        )

    if provider == "openai":
        if not config.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY 未配置")
        print(f"  [Embedding] OpenAI  model={config.OPENAI_EMBEDDING_MODEL}")
        return OpenAIEmbeddings(
            model=config.OPENAI_EMBEDDING_MODEL,
            api_key=config.OPENAI_API_KEY,
        )

    raise ValueError(f"未知 EMBEDDING_PROVIDER='{provider}'，支持：dashscope | openai")
