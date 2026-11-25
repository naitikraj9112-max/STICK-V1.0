"""Shared DeepSeek-compatible chat model configuration."""

from langchain_openai import ChatOpenAI

from config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL, LLM_TIMEOUT_SECONDS


def create_chat_model(temperature: float = 0.0) -> ChatOpenAI:
    """Create a DeepSeek chat model using its OpenAI-compatible API."""
    if not DEEPSEEK_API_KEY:
        raise RuntimeError("DEEPSEEK_API_KEY is missing. Add it to .env before starting the application.")
    return ChatOpenAI(
        model=DEEPSEEK_MODEL,
        api_key=DEEPSEEK_API_KEY,
        base_url=DEEPSEEK_BASE_URL,
        temperature=temperature,
        timeout=LLM_TIMEOUT_SECONDS,
        max_retries=0,
    )
