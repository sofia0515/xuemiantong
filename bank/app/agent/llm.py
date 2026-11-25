"""
模型工厂:创建统一的模型实例
"""

from collections.abc import Callable

from langchain_openai import ChatOpenAI

from app.core.settings import settings

LlmFactory = Callable[[], ChatOpenAI]

def _build_deepseek_model() -> ChatOpenAI:
    if not settings.DEEPSEEK_API_KEY:
        raise ValueError("DEEPSEEK_API_KEY is not set")
    return ChatOpenAI(
        model=settings.DEEPSEEK_MODEL,
        api_key=settings.DEEPSEEK_API_KEY,
        base_url=settings.DEEPSEEK_BASE_URL,
        temperature=settings.DEEPSEEK_TEMPERATURE,
        max_tokens=settings.DEEPSEEK_MAX_TOKENS,
    )

_PROVIDERS_FACTORY : dict[str, LlmFactory] = {
    "deepseek": _build_deepseek_model
}


def get_chat_model(provider:str = "deepseek") -> ChatOpenAI:
    if provider not in _PROVIDERS_FACTORY:
        raise ValueError(f"Invalid provider: {provider}")
    return _PROVIDERS_FACTORY[provider]()


if __name__ == "__main__":
    print(get_chat_model())