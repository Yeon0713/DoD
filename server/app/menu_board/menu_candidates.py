"""LLM 메뉴 후보: 상황(행사·경기·계절의 세부 종류)에 어울리는 메뉴를 HyperCLOVA X 로 고른다.

- 보내는 것은 상황 이름과 매장 메뉴 목록(id, 이름, 종류)뿐이다. 손님 정보나 리뷰는 넣지 않는다.
  메뉴 목록은 JSON 으로 보낸다. 메뉴 이름은 네이버 지도에서 읽어 온 바깥 글이라 줄바꿈이나 지시문이 섞여 있을 수 있는데,
  JSON 이면 이름이 새 줄(가짜 메뉴 줄, 가짜 상황 줄)이 되지 못한다.
- 답은 JSON {"menu_ids": [...], "reason": "..."} 로 받아 검사한다. 이 검사가 마지막 방어선이다.
  - 목록에 없는 id, 겹친 id 는 버리고, 앞에서부터 최대 m = min(5, 메뉴 수)개만 쓴다.
  - 이유 한 줄이 60자를 넘거나 여러 문장·여러 줄이면 첫 문장만 잘라 쓴다(첫 문장이 '~요.'로 끝나고 60자 이하일 때).
    그다음 숫자·% 나 판매 주장(BANNED_REASON_WORDS)이 있으면 "" 로 둔다(후보는 쓴다).
    끝맺음은 '~요.'로 맞춘다: '~요'로 끝나면 마침표를 붙이고, '~요'나 '~요.'로 끝나지 않으면 "" 로 둔다.
    사장님 승인 카드에 그대로 나가므로 근거 없는 숫자를 약속하면 안 된다.
- 실패(키 없음, 연결 오류, 시간 초과, JSON 아님, 남는 id 없음)하면 예외 없이 빈 후보를 돌려준다.
- 성공한 결과만 서버 메모리에 기억한다. 키는 (매장, 세부 종류, 현재 메뉴 id 묶음)이다. 메뉴가 바뀌면 다시 묻는다.

뒤에서 부르기(candidates_in_background): 스냅샷 계산이 CLOVA 를 기다리지 않게, 기억한 결과가 없으면 뒤에서 묻도록 맡기고
바로 빈 후보를 돌려준다. 같은 키는 '진행 중'이면 다시 맡기지 않는다. 결과는 다음 계산 때 쓰인다. 키가 없으면 맡기지 않는다.
실패한 키는 RETRY_AFTER_FAILURE_SECONDS(1시간) 동안 다시 맡기지 않는다(스냅샷을 다시 계산할 때마다 같은 실패를 부르지 않게).

프롬프트 파일: prompts/menu_candidates_prompt.txt. {가게이름}, {업종}, {개수} 를 채운다. 부를 때마다 읽는다.
"""

import json
import logging
import re
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor, wait
from dataclasses import dataclass
from pathlib import Path

import httpx

from app.analysis.input_shapes import Menu
from app.analysis.store_calendar.season import Season
from app.core import clova
from app.core.clova import Post
from app.core.config import settings
from app.planner.data_shapes import EventKind, GameKind

logger = logging.getLogger(__name__)

PROMPT_FILE = Path(__file__).parent / "prompts" / "menu_candidates_prompt.txt"
MAX_CANDIDATES = 5
MAX_REASON_LENGTH = 60  # 프롬프트는 40자 안쪽을 부탁하지만, 조금 넘긴 좋은 이유를 버리지 않으려고 검사는 60자까지 받는다
TEMPERATURE = 0.2  # 결과를 기억해 다시 쓰므로 답이 흔들리지 않게 낮게
MAX_TOKENS = 200
TIMEOUT_SECONDS = 15
CLOVA_FEATURE = "menu_candidates"  # CLOVA 사용 기록(개발자 대시보드 'AI 비용')의 기능 이름
DIGIT_OR_PERCENT_RE = re.compile(r"[\d%％]")  # 전각 숫자도 \d 에 든다
# 판매 데이터를 보지 않은 LLM 의 판매 주장 차단. 상황과 메뉴의 어울림(어울려요, 찾을 만해요, 따뜻해요)은 막지 않는다
BANNED_REASON_WORDS = ("인기", "잘 팔", "많이 팔", "매출", "순위", "베스트", "대박")
SENTENCE_BREAK_RE = re.compile(r"(?<=[.!?])\s+|[\r\n]+")  # 문장 끝(. ! ? 뒤 띄어쓰기) 또는 줄바꿈

MenuBoardKind = EventKind | GameKind | Season  # 메뉴판 교체 계기 태그의 세부 종류

KIND_NAMES: dict[str, str] = {
    "UNIV_FESTIVAL": "대학 축제",
    "LOCAL_FESTIVAL": "지역 축제",
    "LOCAL_EVENT": "동네 행사",
    "MARATHON": "마라톤 대회",
    "BASEBALL": "프로야구 경기",
    "FOOTBALL": "프로축구 경기",
    "NATIONAL_TEAM": "국가대표 경기",
    "ESPORTS": "e스포츠 경기",
    "WINTER": "겨울(추운 날씨)",
    "SUMMER": "여름(더운 날씨)",
}


@dataclass(frozen=True)
class MenuCandidates:
    """menu_ids: 어울리는 순서대로 메뉴 id(문자열). reason: 고른 이유 한 줄(쓸 수 없으면 "")."""

    menu_ids: tuple[str, ...] = ()
    reason: str = ""


EMPTY = MenuCandidates()

BACKGROUND_WORKERS = 2  # 동시에 CLOVA 를 부르는 수. 너무 많으면 요청 한도(429)에 걸린다
RETRY_AFTER_FAILURE_SECONDS = 60 * 60  # 실패한 키를 다시 맡기기까지 기다리는 시간

_Key = tuple[str, str, frozenset[str]]  # (매장, 세부 종류, 메뉴 id 묶음)
_results: dict[_Key, MenuCandidates] = {}
_in_progress: dict[_Key, Future] = {}
_failed_at: dict[_Key, float] = {}  # 뒤에서 물었다가 실패한 시각
_now = time.monotonic  # 테스트에서 시계를 바꿀 수 있게
_guard = threading.Lock()
_executor = ThreadPoolExecutor(max_workers=BACKGROUND_WORKERS, thread_name_prefix="menu-candidates")


def menu_candidates(store: dict, menus: list[Menu], kind: MenuBoardKind, *, post: Post = httpx.post) -> MenuCandidates:
    """store: {"store_id", "name", "category"}. post 는 테스트에서 가짜를 넣는다."""
    if kind not in KIND_NAMES:
        logger.warning("메뉴 후보: 모르는 세부 종류 %r 라 묻지 않는다", kind)
        return EMPTY
    if not menus:
        return EMPTY
    key = _key(store, menus, kind)
    with _guard:
        if key in _results:
            return _results[key]
    try:
        result = _ask(store, menus, kind, post)
    except Exception:  # 후보가 없어도 메뉴판은 데이터 점수만으로 만들 수 있어야 한다
        logger.exception("%s 가게 메뉴 후보 실패: %s", store["store_id"], kind)
        result = EMPTY
    if result.menu_ids:
        with _guard:
            _results[key] = result
    return result


def candidates_in_background(store: dict, menus: list[Menu], kind: MenuBoardKind, *, post: Post = httpx.post) -> MenuCandidates:
    """기억한 후보가 있으면 돌려주고, 없으면 뒤에서 묻도록 맡긴 뒤 빈 후보를 돌려준다. 기다리지 않는다."""
    if kind not in KIND_NAMES or not menus:
        return menu_candidates(store, menus, kind, post=post)  # 묻지 않고 빈 후보(모르는 종류는 경고)
    key = _key(store, menus, kind)
    with _guard:
        if key in _results:
            return _results[key]
        failed_at = _failed_at.get(key)
        waiting = failed_at is not None and _now() - failed_at < RETRY_AFTER_FAILURE_SECONDS
        if settings.clova_studio_api_key and key not in _in_progress and not waiting:
            _in_progress[key] = _executor.submit(_ask_in_background, store, menus, kind, key, post)
    return EMPTY


def _ask_in_background(store: dict, menus: list[Menu], kind: MenuBoardKind, key: "_Key", post: Post) -> None:
    result = EMPTY
    try:
        result = menu_candidates(store, menus, kind, post=post)  # 성공하면 기억한다
    finally:
        with _guard:
            _in_progress.pop(key, None)
            if result.menu_ids:
                _failed_at.pop(key, None)
            else:
                _failed_at[key] = _now()  # 실패는 1시간 뒤에 다시 맡긴다


def wait_for_background(timeout: float = 10) -> None:
    """뒤에서 묻는 중인 일이 끝날 때까지 기다린다 (테스트용)."""
    with _guard:
        futures = list(_in_progress.values())
    wait(futures, timeout=timeout)


def _key(store: dict, menus: list[Menu], kind: MenuBoardKind) -> "_Key":
    return (store["store_id"], kind, frozenset(menu.menu_id for menu in menus))


def load_prompt(store: dict, count: int) -> str:
    """프롬프트 파일을 읽어 {가게이름}, {업종}, {개수} 를 채운다. 매번 읽으므로 파일을 고치면 바로 반영된다."""
    text = PROMPT_FILE.read_text(encoding="utf-8")
    return text.replace("{개수}", str(count)).replace("{가게이름}", store["name"]).replace("{업종}", store["category"])


def user_message(menus: list[Menu], kind: str) -> str:
    """첫 줄 상황, 둘째 줄 안내, 셋째 줄 메뉴 목록 JSON(한 줄)."""
    listed = [{"id": menu.menu_id, "name": menu.name, "category": menu.category} for menu in menus]
    return f"상황: {KIND_NAMES[kind]}\n메뉴 목록(JSON):\n{json.dumps(listed, ensure_ascii=False)}"


def _ask(store: dict, menus: list[Menu], kind: str, post: Post) -> MenuCandidates:
    count = min(MAX_CANDIDATES, len(menus))
    answer = clova.ask(
        load_prompt(store, count),
        user_message(menus, kind),
        max_tokens=MAX_TOKENS,
        temperature=TEMPERATURE,
        timeout=TIMEOUT_SECONDS,
        post=post,
        feature=CLOVA_FEATURE,
        store_id=store["store_id"],
    )
    return _parse(answer, [menu.menu_id for menu in menus], count) if answer else EMPTY


def _parse(answer: str, menu_ids: list[str], count: int) -> MenuCandidates:
    """답에서 첫 { 부터 시작하는 JSON 객체 하나를 읽어 검사한다(앞뒤 글과 뒤따르는 다른 객체는 무시)."""
    start = answer.find("{")
    try:
        data, _ = json.JSONDecoder().raw_decode(answer[start:]) if start >= 0 else (None, 0)
    except ValueError:
        data = None
    if not isinstance(data, dict) or not isinstance(data.get("menu_ids"), list):
        return EMPTY
    known, picked = set(menu_ids), []
    for value in data["menu_ids"]:
        menu_id = str(value) if isinstance(value, (str, int)) and not isinstance(value, bool) else None
        if menu_id in known and menu_id not in picked:
            picked.append(menu_id)
    if not picked:
        return EMPTY
    return MenuCandidates(tuple(picked[:count]), _usable_reason(data.get("reason")))


def _usable_reason(reason) -> str:
    if not isinstance(reason, str):
        return ""
    reason = reason.strip()
    parts = [part.strip() for part in SENTENCE_BREAK_RE.split(reason) if part.strip()]
    if len(parts) > 1 or len(reason) > MAX_REASON_LENGTH:
        first = parts[0] if parts else ""
        if not (first.endswith("요.") and len(first) <= MAX_REASON_LENGTH):
            return ""
        reason = first
    if not reason or DIGIT_OR_PERCENT_RE.search(reason) or any(word in reason for word in BANNED_REASON_WORDS):
        return ""
    if reason.endswith("요."):
        return reason
    return reason + "." if reason.endswith("요") else ""  # 카드 문구 끝맺음을 '~요.'로 맞춘다


def forget_all() -> None:
    """기억한 후보와 진행 중 표시를 모두 지운다 (테스트용). 진행 중이던 일은 끝나도 지운 표시만 다시 지운다."""
    with _guard:
        _results.clear()
        _in_progress.clear()
        _failed_at.clear()
