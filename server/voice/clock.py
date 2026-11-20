"""백엔드가 아는 '지금'. 실제 시계 대신 이 값을 쓴다 (문서 9장 POST /v1/dev/clock).

- set_now 로 정한 시각이 있으면 그 시각, 없으면 실제 서울 시각.
- 작업 큐가 밀린 작업을 돌 때는 그 작업의 예정 시각을 '지금'으로 삼는다 (at). 그래서 시계를 밤 → 아침으로 옮겨도
  밤 21:50 에 돈 바로 답하기는 21:50 에 올린 것으로 적힌다. 이 값은 스레드마다 따로다.
"""

import datetime as dt
import threading
from collections.abc import Iterator
from contextlib import contextmanager

from app.core.seoul_time import SEOUL, now_seoul

_fixed: dt.datetime | None = None
_local = threading.local()


def now() -> dt.datetime:
    override = getattr(_local, "at", None)
    if override is not None:
        return override
    return _fixed if _fixed is not None else now_seoul()


def fixed() -> bool:
    """dev/clock 으로 시계를 멈춰 둔 상태(시연)인가."""
    return _fixed is not None


def set_now(value: dt.datetime | None) -> None:
    global _fixed
    _fixed = value.astimezone(SEOUL) if value is not None else None


@contextmanager
def at(moment: dt.datetime) -> Iterator[None]:
    previous = getattr(_local, "at", None)
    _local.at = moment.astimezone(SEOUL)
    try:
        yield
    finally:
        _local.at = previous


def parse(text: str) -> dt.datetime:
    value = dt.datetime.fromisoformat(text)
    return (value if value.tzinfo else value.replace(tzinfo=SEOUL)).astimezone(SEOUL)


def iso(value: dt.datetime | None) -> str | None:
    return value.astimezone(SEOUL).isoformat(timespec="seconds") if value else None
