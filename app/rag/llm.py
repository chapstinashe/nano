import json
import logging
from typing import Generator, Optional

from openai import AzureOpenAI

from app.core.config import Config

logger = logging.getLogger(__name__)

_client: Optional[AzureOpenAI] = None


def get_azure_client() -> AzureOpenAI:
    global _client
    if _client is None:
        if not Config.AZURE_OPENAI_API_KEY or not Config.AZURE_OPENAI_ENDPOINT:
            raise RuntimeError("Azure OpenAI credentials are not configured")
        _client = AzureOpenAI(
            api_key=Config.AZURE_OPENAI_API_KEY,
            api_version=Config.AZURE_OPENAI_API_VERSION,
            azure_endpoint=Config.AZURE_OPENAI_ENDPOINT,
        )
    return _client


def _is_reasoning_model(deployment: str) -> bool:
    name = deployment.lower()
    return name.startswith("o") or "reasoning" in name


def _completion_kwargs(messages: list[dict[str, str]], stream: bool) -> dict:
    kwargs: dict = {
        "model": Config.AZURE_OPENAI_DEPLOYMENT,
        "messages": messages,
        "stream": stream,
    }
    if _is_reasoning_model(Config.AZURE_OPENAI_DEPLOYMENT):
        kwargs["max_completion_tokens"] = 2000
    else:
        kwargs["temperature"] = 0.2
    return kwargs


def chat_completion(messages: list[dict[str, str]]) -> str:
    client = get_azure_client()
    response = client.chat.completions.create(**_completion_kwargs(messages, stream=False))
    return response.choices[0].message.content or ""


def stream_chat_completion(messages: list[dict[str, str]]) -> Generator[str, None, None]:
    client = get_azure_client()
    stream = client.chat.completions.create(**_completion_kwargs(messages, stream=True))
    for chunk in stream:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        if delta.content:
            yield delta.content


def sse_generator(
    token_generator: Generator[str, None, None],
    results: list | None = None,
    format_sources=None,
) -> Generator[str, None, None]:
    full_answer = ""
    try:
        for token in token_generator:
            full_answer += token
            payload = json.dumps({"token": token})
            yield f"data: {payload}\n\n"
        if results is not None and format_sources is not None:
            sources = format_sources(results, full_answer)
            if sources:
                yield f"data: {json.dumps({'sources': sources})}\n\n"
        yield "data: [DONE]\n\n"
    except Exception as exc:
        logger.exception("LLM streaming failed")
        payload = json.dumps({"error": str(exc)})
        yield f"data: {payload}\n\n"
        yield "data: [DONE]\n\n"
