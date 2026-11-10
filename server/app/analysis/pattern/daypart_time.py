"""시간대 경계와 시각 계산.

기본 경계는 MORNING 오픈~11:00, LUNCH 11:00~17:00, DINNER 17:00~마감이다.
매장 설정(StoreInfo.dayparts)에 사장님이 정한 경계가 있으면 그 값을 쓴다.
모든 시각은 서울 기준이다.
"""

import datetime as dt

from app.analysis.input_shapes import DaypartRange, StoreInfo
from app.core.seoul_time import SEOUL, to_seoul

LUNCH_START = dt.time(11, 0)
DINNER_START = dt.time(17, 0)


def dayparts_of(store: StoreInfo) -> list[DaypartRange]:
    """매장의 시간대 목록(시작 순서). 설정이 없으면 영업시간으로 기본 경계를 만든다."""
    if store.dayparts:
        return sorted(store.dayparts, key=lambda r: r.start)
    return [
        DaypartRange(daypart="MORNING", start=store.open_time, end=LUNCH_START),
        DaypartRange(daypart="LUNCH", start=LUNCH_START, end=DINNER_START),
        DaypartRange(daypart="DINNER", start=DINNER_START, end=store.close_time),
    ]


def daypart_at(t: dt.datetime, ranges: list[DaypartRange]) -> str | None:
    """시각 t 가 속한 시간대. 어느 시간대에도 없으면(영업시간 밖) None."""
    local = to_seoul(t).time()
    for r in ranges:
        if r.start <= local < r.end:
            return r.daypart
    return None


def window(day: dt.date, r: DaypartRange) -> tuple[dt.datetime, dt.datetime]:
    """그 날 그 시간대의 (시작, 끝) 시각."""
    return dt.datetime.combine(day, r.start, SEOUL), dt.datetime.combine(day, r.end, SEOUL)


def overlap_minutes(start_a: dt.datetime, end_a: dt.datetime, start_b: dt.datetime, end_b: dt.datetime) -> float:
    """두 구간이 겹치는 분. 겹치지 않으면 0."""
    seconds = (min(end_a, end_b) - max(start_a, start_b)).total_seconds()
    return max(seconds, 0) / 60


def is_day_finished(day: dt.date, store: StoreInfo, now: dt.datetime) -> bool:
    """그 날 마감 시각이 now 이전이면(같은 시각 포함) 끝난 날이다."""
    return dt.datetime.combine(day, store.close_time, SEOUL) <= to_seoul(now)


def is_closed_day(day: dt.date, store: StoreInfo) -> bool:
    """정기 휴무일인지."""
    return ("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN")[day.weekday()] in store.closed_weekdays
