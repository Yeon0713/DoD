"""GET /v1/home: 앱을 켰을 때. 도나가 무엇을 준비해 뒀는지 (말하지 않는다, say 없음).

v0.2.1 (문서 17장): 머리에 가게 로고·이름·날짜, 그 아래 가게 상태 줄(store_status). 칩(suggestions)은 없다.
"""

import datetime as dt

from fastapi import APIRouter

from voice import clock, hours, repo, speech
from voice.api.errors import store_not_found
from voice.jobs import briefing

router = APIRouter()


def date_label(day: dt.date) -> str:
    return f"{day.month}월 {day.day}일 {speech.weekday(day)}요일"


def time_of(text: str) -> dt.time:
    hour, minute = text.split(":")
    return dt.time(int(hour), int(minute))


def store_clock(text: str) -> str:
    """'10:30' → '오전 10시 30분', '20:30' → '저녁 8시 30분' (가게 상태 줄, 설정 탭). 화면 글이라 '반' 대신 숫자로 (Figma v0.2.1 H, G)."""
    hour, minute = divmod(hours.minutes(text) % (24 * 60), 60)  # "24:00" 은 00:00
    base = speech.clock_label(dt.datetime(2000, 1, 1, hour))
    return f"{base} {minute}분" if minute else base


def store_status(store: dict, now: dt.datetime) -> dict:
    """가게 상태 줄. 그날의 영업시간(설정에서 요일마다 고칠 수 있다)에서 바로 나온다. 시각이 바뀌면 앱이 다시 부른다."""
    found = hours.business_day(store, now)  # 자정 넘김 가게의 새벽은 어제 영업
    today = hours.on(store, now.date())
    tomorrow = hours.on(store, now.date() + dt.timedelta(days=1))
    if found:
        day, hours_ = found
        if now < hours.open_at(day, hours_):
            return {"state": "before_open", "label": "영업 전", "detail": f"{store_clock(hours_['open'])}에 열어요"}
        return {"state": "open", "label": "영업 중", "detail": f"{store_clock(hours_['close'])}에 닫아요"}
    if today is None:
        return {"state": "closed", "label": "쉬는 날", "detail": f"내일 {store_clock(tomorrow['open'])}에 열어요" if tomorrow else "오늘은 쉬어요"}
    # 오늘 문을 닫은 뒤 (Figma v0.2.1 K-01 '영업 끝 밤 8시 30분에 닫았어요')
    return {"state": "closed", "label": "영업 끝", "detail": f"{store_clock(today['close'])}에 닫았어요"}


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
