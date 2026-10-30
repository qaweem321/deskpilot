"""The chat model. Anything with an OpenAI-compatible API works; local llama.cpp is the default."""

from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI

from app.config import Settings


def make_llm(settings: Settings) -> BaseChatModel:
    return ChatOpenAI(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,  # type: ignore[arg-type]
        model=settings.llm_model,
        temperature=0,
        timeout=settings.llm_timeout_seconds,
        max_retries=1,
    )
