"""분석·계획 엔진이 만든 틀 문장을 HyperCLOVA X 로 다듬는다.

흐름
  1. 가게 계산이 끝나면 store_snapshot_cache 가 request_polish() 로 곧 화면에 보일 문장들을 맡긴다.
  2. 뒤에서(스레드 2개) CLOVA X 를 불러 다듬고, 결과를 서버 메모리에 기억한다. 같은 문장은 한 번만 부른다.
  3. 화면용 API 는 polished() 로 다듬은 문장을 꺼낸다. 아직 다듬는 중이거나 실패했으면 원래 문장을 그대로 준다.
     그래서 CLOVA 가 느리거나 꺼져 있어도 화면은 기다리지 않는다.

안전장치: 아래 중 하나라도 걸리면 다듬은 문장을 버리고 원래 문장을 쓴다.
  - 원래 문장의 숫자가 빠졌다
  - 원래 문장에 있던 행사·경기 이름, 요일(must_keep)이 글자 그대로 남아 있지 않다 (예: '춘천 겨울 빛 축제' → '빛 축제')
  - 너무 길거나 여러 줄이다

프롬프트 파일 (말투를 바꾸려면 이 파일들만 고치면 된다. 서버를 다시 켤 필요 없이 다음 다듬기부터 반영된다)
  prompts/calendar_reason_prompt.txt   이번 주 달력 칸의 이유 한 줄
  prompts/plan_card_prompt.txt         할 일 카드 문구 (답글, 메뉴판, 포스터, 반복 불만, 재주문 권유)
  prompts/notice_prompt.txt            승인 없는 알림 (월요일 미리보기, 매출 이상)
프롬프트 안의 {가게이름}, {업종} 은 가게 정보로 바뀐다.
"""

import logging
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable, Iterable, Literal

import httpx

from app.core import clova, clova_usage_log
from app.core.config import settings

logger = logging.getLogger(__name__)

PolishKind = Literal["calendar_reason", "plan_card", "notice"]

PROMPTS_DIR = Path(__file__).parent / "prompts"
PROMPT_FILES: dict[str, str] = {
    "calendar_reason": "calendar_reason_prompt.txt",
    "plan_card": "plan_card_prompt.txt",
    "notice": "notice_prompt.txt",
}
MAX_LENGTH: dict[str, int] = {"calendar_reason": 70, "plan_card": 90, "notice": 120}  # 다듬은 문장 최대 글자 수

WORKERS = 2  # 동시에 CLOVA 를 부르는 수. 너무 많으면 요청 한도(429)에 걸린다
TIMEOUT_SECONDS = 15
NUMBER_RE = re.compile(r"\d+")
PREFIX_RE = re.compile(r"^(-\s*)?(바꾼|다듬은\s*문장|문장|답|결과)\s*[:：]\s*")
QUOTES = "\"'“”‘’「」『』`"

Post = Callable[..., httpx.Response]

_results: dict[tuple[str, str, str], str] = {}  # (종류, 가게 id, 원래 문장) → 다듬은 문장
_in_progress: set[tuple[str, str, str]] = set()
_guard = threading.Lock()
_executor = ThreadPoolExecutor(max_workers=WORKERS, thread_name_prefix="sentence-polish")


def is_enabled() -> bool:
    """설정에서 켜 있고 CLOVA 키가 있을 때만 다듬는다."""
    return settings.sentence_polish_enabled and bool(settings.clova_studio_api_key)


def _key(kind: PolishKind, original: str, store: dict) -> tuple[str, str, str]:
    return (kind, store["store_id"], original)


def polished(kind: PolishKind, original: str, store: dict) -> str:
    """다듬은 문장. 아직 없으면 원래 문장."""
    return _results.get(_key(kind, original, store), original)


def request_polish(kind: PolishKind, originals: Iterable[str], store: dict, must_keep: Iterable[str] = ()) -> None:
    """문장들을 뒤에서 다듬도록 맡긴다. 이미 다듬었거나 다듬는 중인 문장은 건너뛴다.

    must_keep: 원래 문장에 있으면 다듬은 문장에도 글자 그대로 있어야 하는 말 (행사·경기 이름, 요일 등)
    """
    must_keep = tuple(must_keep)
    if not is_enabled():
        return
    for original in dict.fromkeys(originals):  # 같은 문장은 한 번만
        key = _key(kind, original, store)
        with _guard:
            if key in _results or key in _in_progress:
                continue
            _in_progress.add(key)
        _executor.submit(_polish_and_remember, kind, original, store, key, must_keep)


def _polish_and_remember(
    kind: PolishKind, original: str, store: dict, key: tuple[str, str, str], must_keep: tuple[str, ...]
) -> None:
    result = None
    try:
        result = polish_now(kind, original, store, must_keep=must_keep)
    except Exception:  # 다듬기가 실패해도 화면은 원래 문장으로 계속 동작해야 한다
        logger.exception("문장 다듬기 실패: %s", original)
    with _guard:
        _results[key] = result or original  # 실패한 문장도 기억해서 계속 다시 부르지 않는다
        _in_progress.discard(key)


def load_prompt(kind: PolishKind, store: dict) -> str:
    """프롬프트 파일을 읽어 {가게이름}, {업종} 을 채운다. 매번 읽으므로 파일을 고치면 바로 반영된다."""
    text = (PROMPTS_DIR / PROMPT_FILES[kind]).read_text(encoding="utf-8")
    return text.replace("{가게이름}", store["name"]).replace("{업종}", store["category"])


def clean_answer(answer: str) -> str:
    """모델 답에서 문장만 남긴다: 첫 줄, 앞의 '다듬은 문장:' 같은 머리말, 감싼 따옴표를 뗀다."""
    lines = [line.strip() for line in (answer or "").splitlines() if line.strip()]
    if not lines:
        return ""
    text = PREFIX_RE.sub("", lines[0]).strip()
    return text.strip(QUOTES).strip()


def rejection_reason(kind: PolishKind, original: str, candidate: str, must_keep: Iterable[str] = ()) -> str | None:
    """다듬은 문장을 쓰면 안 되는 까닭. 써도 되면 None. (개발자 대시보드 'AI 품질'에 그대로 보인다)"""
    if not candidate:
        return "빈 답"
    if "\n" in candidate:
        return "여러 줄"
    if len(candidate) > MAX_LENGTH[kind]:
        return "너무 김"
    candidate_numbers = NUMBER_RE.findall(candidate)
    if not all(number in candidate_numbers for number in NUMBER_RE.findall(original)):
        return "숫자가 바뀌거나 빠짐"
    if not all(term in candidate for term in must_keep if term and term in original):
        return "행사·경기 이름이나 요일이 바뀜"
    return None


def keeps_facts(kind: PolishKind, original: str, candidate: str, must_keep: Iterable[str] = ()) -> bool:
    """다듬은 문장을 써도 되는지. 숫자와 이름(must_keep)이 그대로 남아 있고, 한 줄이고, 너무 길지 않아야 한다."""
    return rejection_reason(kind, original, candidate, must_keep) is None


def polish_now(
    kind: PolishKind, original: str, store: dict, *, must_keep: Iterable[str] = (), post: Post = httpx.post
) -> str | None:
    """문장 하나를 지금 바로 다듬는다. 실패하거나 검사를 통과하지 못하면 None. post 는 테스트에서 가짜를 넣는다."""
    answer = clova.ask(
        load_prompt(kind, store), original, max_tokens=150, temperature=0.3, timeout=TIMEOUT_SECONDS, post=post,
        feature=f"polish:{kind}", store_id=store.get("store_id"),
    )
    if answer is None:
        return None
    candidate = clean_answer(answer)
    reason = rejection_reason(kind, original, candidate, must_keep)
    clova_usage_log.set_verdict(reason is None, reason)
    return candidate if reason is None else None


def forget_all() -> None:
    """기억한 다듬은 문장을 모두 지운다 (테스트용)."""
    with _guard:
        _results.clear()
