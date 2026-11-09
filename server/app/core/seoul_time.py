"""서울 시간 도구. 서버의 모든 시각은 서울 기준(+09:00)으로 다룬다.

한국은 서머타임이 없어서 +09:00 고정 시간대를 쓴다. (Windows 에서도 추가 설치 없이 동작)
"""

import datetime as dt

SEOUL = dt.timezone(dt.timedelta(hours=9), "Asia/Seoul")


def now_seoul() -> dt.datetime:
    """지금 서울 시각."""
    return dt.datetime.now(SEOUL)


def to_seoul(t: dt.datetime) -> dt.datetime:
    """다른 시간대로 적힌 시각을 서울 시각으로 바꾼다."""
    return t.astimezone(SEOUL)


def at_time(day: dt.date, hhmm: str) -> dt.datetime:
    """날짜와 "14:00" 같은 시각 글자를 합쳐 서울 시각을 만든다."""
    hour, minute = map(int, hhmm.split(":"))
    return dt.datetime(day.year, day.month, day.day, hour, minute, tzinfo=SEOUL)


def is_within_dates(day: dt.date, from_date: dt.date | None, to_date: dt.date | None) -> bool:
    """day 가 from_date ~ to_date 안에 있는지(양 끝 포함). 비어 있는 쪽은 제한하지 않는다."""
    return (from_date is None or day >= from_date) and (to_date is None or day <= to_date)
