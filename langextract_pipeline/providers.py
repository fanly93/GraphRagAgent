"""OpenAI-compatible 模型接入层。

通过 openai SDK 的 base_url 参数，以标准 OpenAI 接口协议对接：
  - DashScope（阿里云）：Qwen 系列模型
  - DeepSeek：deepseek-chat 等模型

使用方式：直接将 create_model() 返回的实例传给 lx.extract(model=...) 即可，
无需修改 langextract 内部路由规则。
"""

import config
from langextract.providers.openai import OpenAILanguageModel


def create_dashscope_model(model_id: str | None = None) -> OpenAILanguageModel:
    """构建 DashScope Qwen 模型客户端（OpenAI-compatible 接口）。

    DashScope OpenAI-compatible base_url:
        https://dashscope.aliyuncs.com/compatible-mode/v1

    常用 model_id（填入 .env KG_MODEL_ID）：
        qwen-plus          Qwen Plus（均衡性能，推荐首选）
        qwen-turbo         Qwen Turbo（低延迟，适合长文档批量）
        qwen-max           Qwen Max（最强能力）
        qwen3-235b-a22b    Qwen3 旗舰多模态（需确认 DashScope 接口支持）
    """
    api_key = config.DASHSCOPE_API_KEY
    if not api_key:
        raise ValueError("DASHSCOPE_API_KEY 未配置，无法创建 DashScope 模型。")

    return OpenAILanguageModel(
        model_id=model_id or config.KG_MODEL_ID,
        api_key=api_key,
        base_url=config.DASHSCOPE_BASE_URL,
        max_workers=config.MAX_WORKERS,
    )


def create_deepseek_model(model_id: str | None = None) -> OpenAILanguageModel:
    """构建 DeepSeek 模型客户端（OpenAI-compatible 接口）。

    DeepSeek base_url: https://api.deepseek.com/v1

    常用 model_id：
        deepseek-chat      DeepSeek-V3（通用对话，推荐）
        deepseek-reasoner  DeepSeek-R1（推理增强，速度较慢）
    """
    api_key = config.DEEPSEEK_API_KEY
    if not api_key:
        raise ValueError("DEEPSEEK_API_KEY 未配置，无法创建 DeepSeek 模型。")

    return OpenAILanguageModel(
        model_id=model_id or config.KG_MODEL_ID,
        api_key=api_key,
        base_url=config.DEEPSEEK_BASE_URL,
        max_workers=config.MAX_WORKERS,
    )


def create_model() -> OpenAILanguageModel:
    """根据 KG_MODEL_PROVIDER 配置创建对应的模型实例。

    优先级：KG_MODEL_PROVIDER → dashscope（默认）

    Returns:
        配置好的 OpenAILanguageModel 实例，可直接传给 lx.extract(model=...)
    """
    provider = config.KG_MODEL_PROVIDER.lower()
    if provider == "deepseek":
        model = create_deepseek_model()
        print(f"[Provider] DeepSeek  model_id={model.model_id}  base_url={config.DEEPSEEK_BASE_URL}")
    elif provider == "dashscope":
        model = create_dashscope_model()
        print(f"[Provider] DashScope  model_id={model.model_id}  base_url={config.DASHSCOPE_BASE_URL}")
    else:
        raise ValueError(
            f"未知 KG_MODEL_PROVIDER='{provider}'，支持：dashscope | deepseek"
        )
    return model
