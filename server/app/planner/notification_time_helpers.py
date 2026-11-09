"""알림 시간 계산 도우미. 규칙 파일들이 같이 쓴다.

알림 가능 시각은 매장 설정의 slots(기본 10:00 출근 후, 14:00 오후, 21:30 마감 전)이다.
"""

import datetime as dt

from app.core.seoul_time import at_time, to_seoul
from app.planner.data_shapes import SlotName, StoreSettings

WEEKDAY_CODES = ("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN")
KOREAN_WEEKDAYS = ("월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일")

# 다음 알림 시간을 찾을 때 며칠 뒤까지 볼지
SEARCH_DAYS = 14


def slot_at(day: dt.date, slot_name: SlotName, store: StoreSettings) -> dt.datetime:
    """그 날의 특정 알림 시각. 예) slot_at(11/16, "AFTERNOON") → 11/16 14:00"""
    return at_time(day, getattr(store.slots, slot_name))


def slot_times_on(day: dt.date, store: StoreSettings) -> list[tuple[SlotName, dt.datetime]]:
    """그 날의 알림 가능 시각 목록(시간순). 휴무일이면 빈 목록."""
    if WEEKDAY_CODES[day.weekday()] in store.closed_weekdays:
        return []
    return [(name, slot_at(day, name, store)) for name in ("OPENING", "AFTERNOON", "CLOSING")]


def next_slot(t: dt.datetime, store: StoreSettings, *, include_same_time: bool = False) -> dt.datetime:
    """t 다음의 알림 가능 시각. include_same_time=True 면 t 와 같은 시각도 포함한다.

    예) 11/17 12:30 → 11/17 14:00, 11/17 21:40 → 11/18 10:00
    """
    t = to_seoul(t)
    for offset in range(SEARCH_DAYS):
        day = t.date() + dt.timedelta(days=offset)
        for _, slot_time in slot_times_on(day, store):
            if slot_time > t or (include_same_time and slot_time == t):
                return slot_time
    raise ValueError(f"{t} 뒤 {SEARCH_DAYS}일 안에 알림 가능 시각이 없습니다.")


def next_named_slot(
    t: dt.datetime, slot_name: SlotName, store: StoreSettings, *, include_same_time: bool = False
) -> dt.datetime:
    """t 다음의 특정 알림 시각. 예) '발견 뒤 첫 14:00' 은 next_named_slot(t, "AFTERNOON")"""
    t = to_seoul(t)
    for offset in range(SEARCH_DAYS):
        day = t.date() + dt.timedelta(days=offset)
        for name, slot_time in slot_times_on(day, store):
            if name == slot_name and (slot_time > t or (include_same_time and slot_time == t)):
                return slot_time
    raise ValueError(f"{t} 뒤 {SEARCH_DAYS}일 안에 {slot_name} 알림 시각이 없습니다.")


def slot_name_of(t: dt.datetime, store: StoreSettings) -> SlotName | None:
    """t 가 알림 가능 시각이면 그 이름(OPENING 등), 아니면 None."""
    t = to_seoul(t)
    for name, slot_time in slot_times_on(t.date(), store):
        if slot_time == t:
            return name
    return None


def postpone_if_passed(approval_at: dt.datetime, known_at: dt.datetime, store: StoreSettings) -> dt.datetime:
    """승인 요청 시각이 근거를 알게 된 시각보다 이르면(이미 지났으면) 다음 알림 시각으로 미룬다."""
    if approval_at >= known_at:
        return approval_at
    return next_slot(known_at, store, include_same_time=True)


def saturday_of_week(day: dt.date) -> dt.date:
    """day 가 속한 주(월~일)의 토요일. 일요일이면 하루 전 토요일이다."""
    return day + dt.timedelta(days=5 - day.weekday())


def close_time_on(day: dt.date, store: StoreSettings) -> dt.datetime:
    """그 날 영업 마감 시각."""
    return at_time(day, store.close_time)
