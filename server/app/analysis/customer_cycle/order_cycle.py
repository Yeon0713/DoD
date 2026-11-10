"""손님 주문 주기(customer_cycle)를 만든다.

- 손님 키(customer_key)가 있는 now 이전 주문만 쓴다. 하루에 여러 번 주문하면 그날 첫 주문 하나만 방문으로 센다.
- 방문이 4번보다 적으면 NONE 이다. 간격은 최근 4번 방문 사이의 날짜 차이 3개(오래된 것부터)다.
- WEEKLY: 최근 4번 중 3번 이상이 같은 요일·같은 시간대이고, 간격 3개 중 2개 이상이 5~9일. 먼저 본다.
- MONTHLY: 간격 3개 중 2개 이상이 25~35일.
- 마지막 방문이 오래된 손님(WEEKLY 21일, MONTHLY 70일 넘게)은 끊긴 것으로 보고 NONE 이다.
- 다음 예상: WEEKLY 는 마지막 방문 다음의 그 요일, 시각은 그 요일 방문 시각의 중앙값.
  MONTHLY 는 마지막 방문에서 28일 뒤 같은 시각.
"""

import datetime as dt
import statistics
from collections import Counter, defaultdict

from app.analysis.input_shapes import AnalysisInputs, DaypartRange, Order
from app.analysis.pattern.daypart_time import daypart_at, dayparts_of
from app.analysis.result_shapes import CustomerCycleRow
from app.core.seoul_time import SEOUL, to_seoul

MIN_VISITS = 4  # 주기를 판단하는 최소 방문 수
RECENT_VISITS = 4  # 요일과 간격을 보는 최근 방문 수
WEEKLY_GAP_DAYS = (5, 9)
MONTHLY_GAP_DAYS = (25, 35)
MIN_MATCHING = 3  # 최근 4번 중 같은 요일·시간대여야 하는 방문 수
MIN_MATCHING_GAPS = 2  # 간격 3개 중 기준에 맞아야 하는 수
MONTHLY_NEXT_DAYS = 28
STALE_DAYS = {"WEEKLY": 21, "MONTHLY": 70}  # 마지막 방문이 이보다 오래되면 NONE


def visits_by_customer(orders: list[Order], now: dt.datetime) -> dict[str, list[dt.datetime]]:
    """손님 → 방문 시각 목록(시간순). 하루에 여러 번 주문하면 그날 첫 주문만 남긴다."""
    first_of_day: dict[str, dict[dt.date, dt.datetime]] = defaultdict(dict)
    for order in sorted(orders, key=lambda o: o.ordered_at):
        if order.customer_key is None or order.ordered_at > now:
            continue
        at = to_seoul(order.ordered_at)
        first_of_day[order.customer_key].setdefault(at.date(), at)
    return {key: sorted(days.values()) for key, days in first_of_day.items()}


def _gaps(visits: list[dt.datetime]) -> list[int]:
    dates = [v.date() for v in visits]
    return [(b - a).days for a, b in zip(dates, dates[1:])]


def _count_in(gaps: list[int], bounds: tuple[int, int]) -> int:
    low, high = bounds
    return sum(low <= gap <= high for gap in gaps)


def _median_time(times: list[dt.datetime]) -> dt.time:
    """시각들의 하루 중 중앙값(분 단위 반올림)."""
    minutes = statistics.median(t.hour * 60 + t.minute + t.second / 60 for t in times)
    minutes = round(minutes)
    return dt.time(minutes // 60, minutes % 60)


def _weekly_pattern(recent: list[dt.datetime], ranges: list[DaypartRange]) -> list[dt.datetime] | None:
    """최근 방문 중 같은 요일·같은 시간대인 방문이 3번 이상이면 그 방문들, 아니면 None."""
    groups = Counter((v.weekday(), daypart_at(v, ranges)) for v in recent)
    (weekday, daypart), count = groups.most_common(1)[0]
    if count < MIN_MATCHING or daypart is None:
        return None
    return [v for v in recent if (v.weekday(), daypart_at(v, ranges)) == (weekday, daypart)]


def classify_customer(
    customer_key: str, visits: list[dt.datetime], now: dt.datetime, ranges: list[DaypartRange]
) -> CustomerCycleRow:
    recent = visits[-RECENT_VISITS:]
    gaps = _gaps(recent)

    def row(cycle: str, next_at: dt.datetime | None = None) -> CustomerCycleRow:
        return CustomerCycleRow(
            customer_key=customer_key,
            cycle=cycle,
            next_expected_at=next_at,
            expected_daypart=daypart_at(next_at, ranges) if next_at else None,
            intervals_days=gaps,
            computed_at=now,
        )

    if len(visits) < MIN_VISITS:
        return row("NONE")
    last = recent[-1]
    days_since_last = (to_seoul(now).date() - last.date()).days

    same = _weekly_pattern(recent, ranges)
    if same and _count_in(gaps, WEEKLY_GAP_DAYS) >= MIN_MATCHING_GAPS:
        if days_since_last > STALE_DAYS["WEEKLY"]:
            return row("NONE")
        weekday = same[0].weekday()
        next_day = last.date() + dt.timedelta(days=(weekday - last.weekday() - 1) % 7 + 1)
        return row("WEEKLY", dt.datetime.combine(next_day, _median_time(same), SEOUL))

    if _count_in(gaps, MONTHLY_GAP_DAYS) >= MIN_MATCHING_GAPS:
        if days_since_last > STALE_DAYS["MONTHLY"]:
            return row("NONE")
        return row("MONTHLY", last + dt.timedelta(days=MONTHLY_NEXT_DAYS))

    return row("NONE")


def build_customer_cycles(inputs: AnalysisInputs, now: dt.datetime) -> list[CustomerCycleRow]:
    """now 기준으로 주문한 적 있는 모든 손님의 주기. 손님 키 순서."""
    ranges = dayparts_of(inputs.store)
    visits = visits_by_customer(inputs.orders, now)
    return [classify_customer(key, visits[key], now, ranges) for key in sorted(visits)]
