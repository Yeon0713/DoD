"""HyperCLOVA X (CLOVA Studio) 호출."""

import httpx

from app.core.config import settings


def chat(messages: list[dict[str, str]], max_tokens: int = 256) -> httpx.Response:
    """messages 예) [{"role": "user", "content": "안녕"}]"""
    return httpx.post(
        f"{settings.clova_studio_base_url}/v3/chat-completions/{settings.clova_studio_model}",
        headers={"Authorization": f"Bearer {settings.clova_studio_api_key}"},
        json={
            "messages": [
                {"role": m["role"], "content": [{"type": "text", "text": m["content"]}]}
                for m in messages
            ],
            "maxTokens": max_tokens,
        },
        timeout=settings.clova_studio_timeout,
    )
