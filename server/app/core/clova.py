"""HyperCLOVA X (CLOVA Studio) 호출."""

import logging
import time
import uuid
from typing import Callable

import httpx

from app.core import clova_usage_log
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


def token_usage(response: httpx.Response) -> tuple[int | None, int | None]:
    """v3 응답의 (입력 토큰, 출력 토큰). 응답에 usage 가 없으면 (None, None)."""
    try:
        usage = response.json()["result"]["usage"]
        return int(usage["promptTokens"]), int(usage["completionTokens"])
    except (ValueError, KeyError, TypeError):
        return None, None


def ask(
    system: str,
    user: str,
    *,
    max_tokens: int = 256,
    temperature: float = 0.5,
    timeout: float = 15,
    post: Post = httpx.post,
    feature: str = "other",
    store_id: str | None = None,
) -> str | None:
    """시스템 프롬프트와 사용자 글 하나로 묻고 답 글자를 돌려준다.

    키가 없거나, 연결이 실패하거나, 200 이 아니면 None. post 는 테스트에서 가짜를 넣으려고 받는다.
    부를 때마다 clova_usage_log 에 기능(feature), 가게, 토큰 수, 걸린 시간을 남긴다 (개발자 대시보드 'AI 비용').
    """
    if not settings.clova_studio_api_key:
        return None
    started = time.perf_counter()

    def log(status: str, http_status: int | None, response: httpx.Response | None, answer: str | None) -> None:
        input_tokens, output_tokens = token_usage(response) if response is not None else (None, None)
        try:
            clova_usage_log.record_call(
                feature=feature,
                store_id=store_id,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                latency_ms=round((time.perf_counter() - started) * 1000),
                status=status,
                http_status=http_status,
                request_text=user,
                answer_text=answer,
            )
        except Exception:  # 기록이 실패해도 CLOVA 답은 그대로 쓴다
            logger.exception("CLOVA 사용 기록 실패")

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
        log("connection_error", None, None, None)
        return None
    if response.status_code != 200:
        logger.warning("CLOVA 응답 %s", response.status_code)
        log("http_error", response.status_code, None, None)
        return None
    answer = answer_text(response)
    log("ok", 200, response, answer)
    return answer
