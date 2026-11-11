"""시간대 경계와 시각 계산.

기본 경계는 MORNING 오픈~11:00, LUNCH 11:00~17:00, DINNER 17:00~마감이다.
영업시간과 겹치지 않는 시간대는 뺀다. 예) 17:00 오픈이면 DINNER 하나, 12:00 오픈이면 LUNCH·DINNER
매장 설정(StoreInfo.dayparts)에 사장님이 정한 경계가 있으면 그 값을 쓴다.
모든 시각은 서울 기준이다.

자정을 넘겨 영업하는 매장(예: 17:00~03:00)은 영업일로 묶는다.
마감 전 새벽 시각(1/2 01:00)은 전날(1/1) 영업일에 속하고, 시간대도 자정을 넘을 수 있다(DINNER 17:00~03:00).
"""

import datetime as dt

from app.analysis.input_shapes import DaypartRange, StoreInfo
from app.core.seoul_time import SEOUL, to_seoul

LUNCH_START = dt.time(11, 0)
DINNER_START = dt.time(17, 0)
DAY_MINUTES = 24 * 60


def _minutes(t: dt.time) -> int:
    return t.hour * 60 + t.minute


def _time(minutes: int) -> dt.time:
    minutes %= DAY_MINUTES
    return dt.time(minutes // 60, minutes % 60)


def dayparts_of(store: StoreInfo) -> list[DaypartRange]:
    """매장의 시간대 목록(영업 시작부터 순서대로). 설정이 없으면 영업시간으로 기본 경계를 만든다."""
    open_at = _minutes(store.open_time)
    if store.dayparts:
        return sorted(store.dayparts, key=lambda r: (_minutes(r.start) - open_at) % DAY_MINUTES)
    # 오픈한 날 0시부터 센 분. 자정 넘는 마감은 24*60 을 더한다.
    close_at = _minutes(store.close_time) + (DAY_MINUTES if store.overnight else 0)
    lunch_at, dinner_at = _minutes(LUNCH_START), _minutes(DINNER_START)
    bounds = [
        ("MORNING", open_at, min(lunch_at, close_at)),
        ("LUNCH", max(open_at, lunch_at), min(dinner_at, close_at)),
        ("DINNER", max(open_at, dinner_at), close_at),
    ]
    return [DaypartRange(daypart=name, start=_time(s), end=_time(e)) for name, s, e in bounds if s < e]


def daypart_at(t: dt.datetime, ranges: list[DaypartRange]) -> str | None:
    """시각 t 가 속한 시간대. 어느 시간대에도 없으면(영업시간 밖) None."""
    local = to_seoul(t).time()
    for r in ranges:
        if r.start < r.end:
            inside = r.start <= local < r.end
        else:  # 자정을 넘는 시간대
            inside = local >= r.start or local < r.end
        if inside:
            return r.daypart
    return None


def business_date(t: dt.datetime, store: StoreInfo) -> dt.date:
    """시각 t 가 속한 영업일. 자정 넘어 영업하는 매장의 마감 전 새벽은 전날이다."""
    local = to_seoul(t)
    if store.overnight and local.time() < store.close_time:
        return local.date() - dt.timedelta(days=1)
    return local.date()


def at_business_time(day: dt.date, t: dt.time, store: StoreInfo) -> dt.datetime:
    """영업일 day 의 시각 t. 자정 넘어 영업하는 매장에서 오픈보다 이른 시각은 다음 날 새벽이다."""
    at = dt.datetime.combine(day, t, SEOUL)
    if store.overnight and t < store.open_time:
        at += dt.timedelta(days=1)
    return at


def window(day: dt.date, r: DaypartRange, store: StoreInfo) -> tuple[dt.datetime, dt.datetime]:
    """그 영업일 그 시간대의 (시작, 끝) 시각."""
    return at_business_time(day, r.start, store), at_business_time(day, r.end, store)


def overlap_minutes(start_a: dt.datetime, end_a: dt.datetime, start_b: dt.datetime, end_b: dt.datetime) -> float:
    """두 구간이 겹치는 분. 겹치지 않으면 0."""
    seconds = (min(end_a, end_b) - max(start_a, start_b)).total_seconds()
    return max(seconds, 0) / 60


def is_day_finished(day: dt.date, store: StoreInfo, now: dt.datetime) -> bool:
    """그 영업일 마감 시각이 now 이전이면(같은 시각 포함) 끝난 날이다."""
    return at_business_time(day, store.close_time, store) <= to_seoul(now)


def is_closed_day(day: dt.date, store: StoreInfo) -> bool:
    """정기 휴무일인지. day 는 영업일이다."""
    return ("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN")[day.weekday()] in store.closed_weekdays
