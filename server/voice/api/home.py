"""GET /v1/home: 앱을 켰을 때. 도나가 무엇을 준비해 뒀는지 (말하지 않는다, say 없음).

v0.2.1 (문서 17장): 머리에 가게 로고·이름·날짜, 그 아래 가게 상태 줄(store_status). 칩(suggestions)은 없다.
"""

import datetime as dt

from fastapi import APIRouter

from voice import clock, repo, speech
from voice.api.errors import store_not_found
from voice.jobs import briefing

router = APIRouter()


def date_label(day: dt.date) -> str:
    return f"{day.month}월 {day.day}일 {speech.weekday(day)}요일"


def time_of(text: str) -> dt.time:
    hour, minute = text.split(":")
    return dt.time(int(hour), int(minute))


def store_clock(text: str) -> str:
    """'10:30' → '오전 10시 30분' (가게 상태 줄, 설정 탭)."""
    t = time_of(text)
    return speech.clock_label(dt.datetime(2000, 1, 1, t.hour, t.minute))


def store_status(store: dict, now: dt.datetime) -> dict:
    """가게 상태 줄. 영업시간에서 바로 나온다. 시각이 바뀌면 앱이 다시 부른다."""
    t = now.time().replace(tzinfo=None)
    if t < time_of(store["open_time"]):
        return {"state": "before_open", "label": "영업 전", "detail": f"{store_clock(store['open_time'])}에 열어요"}
    if t < time_of(store["close_time"]):
        return {"state": "open", "label": "영업 중", "detail": f"{store_clock(store['close_time'])}에 닫아요"}
    return {"state": "closed", "label": "영업 끝", "detail": f"내일 {store_clock(store['open_time'])}에 열어요"}


def store_block(store: dict) -> dict:
    return {"id": store["id"], "name": store["name"], "logo_url": store.get("logo_url"),
            "open_time": store["open_time"], "close_time": store["close_time"]}


@router.get("/home")
def home(store_id: str):
    store = repo.store(store_id)
    if store is None:
        return store_not_found()
    now = clock.now()
    brief = briefing.current(store_id)
    body = {
        "store": store_block(store),
        "date": now.date().isoformat(),
        "date_label": date_label(now.date()),
        "store_status": store_status(store, now),
        "now": clock.iso(now),
        "briefing_ready": brief is not None,
        "prepared_at": brief["prepared_at"] if brief else None,
    }
    if brief is None:  # 준비 전 홈 (14장 6번 제안)
        return {**body, "headline": "아직 준비하고 있어요", "cards": []}
    return {**body, "headline": "오늘 일정 브리핑 준비했어요",
            "cards": [{"type": "rows", "id": "prepared", "rows": brief["home_rows"]}]}
