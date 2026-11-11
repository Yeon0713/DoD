"""기준선(평소 매출)을 구한다.

기준선은 특별한 칸을 뺀, 최근 8주 같은 요일·같은 시간대 칸 매출의 중앙값이다.
- 기준일(as_of) 이전 8주 안의 같은 요일만 쓴다. 기준일 당일은 넣지 않는다.
- 입력은 sales_daily 행이라 now 이전·마감이 지난 날만 들어 있다.
- 특별한 칸을 빼고 남은 주가 4주 미만이면 기준선이 없다(None).
"""

import datetime as dt

from app.analysis.pattern.daypart_time import weekday_of
from app.analysis.result_shapes import AnalysisDaypart, SalesDailyRow
from app.planner.data_shapes import Weekday

Cell = tuple[dt.date, AnalysisDaypart]  # 칸: 날짜 × 시간대

WINDOW = dt.timedelta(weeks=8)
MIN_WEEKS = 4  # 특별한 칸을 빼고 남은 주가 이보다 적으면 기준선이 없다(None)


def baseline_for(
    rows: list[SalesDailyRow],
    excluded: set[Cell],
    day: dt.date,
    daypart: AnalysisDaypart,
) -> int | None:
    """day 의 daypart 칸 기준선. day 직전 8주의 같은 요일 칸을 쓴다."""
    values = [
        r.sales_amount
        for r in rows
        if r.daypart == daypart
        and r.date.weekday() == day.weekday()
        and day - WINDOW <= r.date < day
        and (r.date, r.daypart) not in excluded
    ]
    if len(values) < MIN_WEEKS:
        return None
    return _median_half_up(values)


def build_baselines(
    rows: list[SalesDailyRow],
    excluded: set[Cell],
    as_of: dt.date,
    dayparts: list[AnalysisDaypart],
) -> dict[tuple[Weekday, AnalysisDaypart], int | None]:
    """요일 × 시간대 모든 칸의 기준선. as_of 이전 8주(as_of 당일 제외)의 같은 요일 칸을 쓴다.

    calendar_day 는 as_of = 오늘로 부르고, 앞날의 칸은 같은 요일·시간대 값을 그대로 쓴다.
    """
    result = {}
    for offset in range(7):
        target = as_of + dt.timedelta(days=offset)  # as_of 이후 그 요일의 첫 날. 직전 8주가 모두 as_of 이전이다
        for daypart in dayparts:
            result[(weekday_of(target), daypart)] = baseline_for(rows, excluded, target, daypart)
    return result


def _median_half_up(values: list[int]) -> int:
    """정수 중앙값. 개수가 짝수면 가운데 두 값의 평균이고, .5 는 올린다."""
    s = sorted(values)
    mid = len(s) // 2
    if len(s) % 2:
        return s[mid]
    return (s[mid - 1] + s[mid] + 1) // 2
