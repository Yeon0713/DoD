"""HyperCLOVA X (CLOVA Studio) 호출."""

import logging
import uuid
from typing import Callable

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

Post = Callable[..., httpx.Response]


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


def answer_text(response: httpx.Response) -> str:
    """v3 응답에서 답 글자만 꺼낸다. 모양이 다르면 빈 글자."""
    try:
        content = response.json()["result"]["message"]["content"]
    except (ValueError, KeyError, TypeError):
        return ""
    if isinstance(content, list):  # 글자 조각 목록으로 올 때
        content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
    return content if isinstance(content, str) else ""


def ask(
    system: str,
    user: str,
    *,
    max_tokens: int = 256,
    temperature: float = 0.5,
    timeout: float = 15,
    post: Post = httpx.post,
) -> str | None:
    """시스템 프롬프트와 사용자 글 하나로 묻고 답 글자를 돌려준다.

    키가 없거나, 연결이 실패하거나, 200 이 아니면 None. post 는 테스트에서 가짜를 넣으려고 받는다.
    """
    if not settings.clova_studio_api_key:
        return None
    try:
        response = post(
            f"{settings.clova_studio_base_url}/v3/chat-completions/{settings.clova_studio_model}",
            headers={
                "Authorization": f"Bearer {settings.clova_studio_api_key}",
                "Content-Type": "application/json",
                "X-NCP-CLOVASTUDIO-REQUEST-ID": uuid.uuid4().hex,
            },
            json={
                "messages": [
                    {"role": "system", "content": [{"type": "text", "text": system}]},
                    {"role": "user", "content": [{"type": "text", "text": user}]},
                ],
                "maxTokens": max_tokens,
                "temperature": temperature,
                "topP": 0.8,
            },
            timeout=timeout,
        )
    except httpx.HTTPError as error:
        logger.warning("CLOVA 연결 실패: %s", error)
        return None
    if response.status_code != 200:
        logger.warning("CLOVA 응답 %s", response.status_code)
        return None
    return answer_text(response)
