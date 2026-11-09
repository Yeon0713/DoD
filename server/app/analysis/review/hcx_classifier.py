"""HyperCLOVA X 로 리뷰 한 건을 분류한다.

- 모델에는 리뷰 본문만 보낸다. 전화번호와 @닉네임은 보내기 전에 가린다.
- 답은 {"sentiment": ..., "complaint_types": [...]} JSON 이어야 한다. 모양이 틀리면 한 번 더 묻는다.
- 두 번 모두 실패하면 None 을 돌려준다. 부르는 쪽이 키워드 규칙으로 대신한다.

app/core/clova.py 의 chat() 은 temperature 같은 값을 받지 않아서 여기서 직접 요청한다.
"""

import json
import re
import time
import uuid
from collections.abc import Callable
from pathlib import Path

import httpx

from app.analysis.review.complaint_groups import COMPLAINT_TYPES, sort_types
from app.core.config import settings

PROMPT = (Path(__file__).parent / "prompts" / "review_label.txt").read_text(encoding="utf-8")
SENTIMENTS = ("POSITIVE", "NEGATIVE", "MIXED")

TIMEOUT_SECONDS = 10  # 한 번 묻는 데 기다리는 최대 시간. 평소 응답은 1~2초
MAX_ATTEMPTS = 2  # 처음 한 번 + 다시 한 번
RATE_LIMIT_WAIT_SECONDS = 10  # 호출 한도(분당 요청 수)에 걸렸을 때(HTTP 429) 기다리는 시간

PHONE_RE = re.compile(r"01[016789][-.\s]?\d{3,4}[-.\s]?\d{4}")
MENTION_RE = re.compile(r"@[^\s@]+")
JSON_RE = re.compile(r"\{.*\}", re.S)

Post = Callable[..., httpx.Response]


def mask_personal_info(text: str) -> str:
    """전화번호와 @닉네임을 가린다."""
    return MENTION_RE.sub("@***", PHONE_RE.sub("***-****-****", text))


def parse_answer(answer: str) -> tuple[str, list[str]] | None:
    """모델 답에서 (감정, 불만 유형 목록)을 꺼낸다. 모양이 틀리면 None.

    - 코드 블록(```json)이나 앞뒤 글이 붙어 와도 처음 { 부터 마지막 } 까지 읽는다.
    - 불만 유형은 중복을 빼고 정해진 순서로 정렬한다.
    - 불만 유형이 있는데 POSITIVE 라고 답하면 MIXED 로 고친다.
    """
    match = JSON_RE.search(answer or "")
    if match is None:
        return None
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    sentiment, types = data.get("sentiment"), data.get("complaint_types")
    if sentiment not in SENTIMENTS or not isinstance(types, list):
        return None
    if not all(t in COMPLAINT_TYPES for t in types):
        return None
    types = sort_types(types)
    if types and sentiment == "POSITIVE":
        sentiment = "MIXED"
    return sentiment, types


def _answer_text(response: httpx.Response) -> str:
    """v3 응답에서 답 글자만 꺼낸다. 모양이 다르면 빈 글자."""
    try:
        content = response.json()["result"]["message"]["content"]
    except (ValueError, KeyError, TypeError):
        return ""
    if isinstance(content, list):  # 글자 조각 목록으로 올 때
        content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
    return content if isinstance(content, str) else ""


def _request_body(text: str) -> dict:
    return {
        "messages": [
            {"role": "system", "content": [{"type": "text", "text": PROMPT}]},
            {"role": "user", "content": [{"type": "text", "text": mask_personal_info(text)}]},
        ],
        "maxTokens": 100,
        "temperature": 0.1,
        "topP": 0.8,
    }


def classify_with_hcx(
    text: str,
    *,
    post: Post = httpx.post,
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[str, list[str]] | None:
    """리뷰 본문 하나 → (감정, 불만 유형 목록). 실패하면 None.

    post, sleep 은 테스트에서 가짜를 넣으려고 받는다.
    """
    if not settings.clova_studio_api_key:
        return None
    url = f"{settings.clova_studio_base_url}/v3/chat-completions/{settings.clova_studio_model}"
    body = _request_body(text)
    for _ in range(MAX_ATTEMPTS):
        headers = {
            "Authorization": f"Bearer {settings.clova_studio_api_key}",
            "Content-Type": "application/json",
            "X-NCP-CLOVASTUDIO-REQUEST-ID": uuid.uuid4().hex,
        }
        try:
            response = post(url, headers=headers, json=body, timeout=TIMEOUT_SECONDS)
        except httpx.HTTPError:  # 연결 실패, 시간 초과
            continue
        if response.status_code == 429:
            sleep(RATE_LIMIT_WAIT_SECONDS)
            continue
        if response.status_code != 200:
            continue
        parsed = parse_answer(_answer_text(response))
        if parsed is not None:
            return parsed
    return None
