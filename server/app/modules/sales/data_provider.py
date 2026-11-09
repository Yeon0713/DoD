"""매출 패턴 데이터 가져오기.

응답 예시(sales_response.example.json)는 하루 × 시간대 단위(grain=day)로 적혀 있고,
요청한 단위(week, month, weekday_daypart)로 여기서 묶는다.
태성의 분석 결과(sales_daily)가 나오면 그걸 읽도록 바꾸고, 묶는 방법은 그대로 쓴다.
"""

import datetime as dt
from collections import defaultdict

from app.core.sample_response_loader import load_sample_response
from app.core.seoul_time import is_within_dates
from app.modules.sales.response_format import Grain, SalesResponse, SalesRow

AMOUNT_FIELDS = ("sales_amount", "qty", "food_cost", "labor_cost", "profit")
WEEKDAY_CODES = ("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN")
DAYPART_ORDER = ("LUNCH", "DINNER", "NIGHT")


def get_sales(from_date: dt.date | None, to_date: dt.date | None, grain: Grain) -> SalesResponse:
    daily = SalesResponse.model_validate(load_sample_response("sales"))
    rows = [row for row in daily.rows if is_within_dates(dt.date.fromisoformat(row.period), from_date, to_date)]
    return SalesResponse(is_example=daily.is_example, grain=grain, rows=_group_rows(rows, grain))


def _period_of(day: dt.date, grain: Grain) -> str:
    if grain == "day":
        return day.isoformat()
    if grain == "week":
        return (day - dt.timedelta(days=day.weekday())).isoformat()
    if grain == "month":
        return day.strftime("%Y-%m")
    return WEEKDAY_CODES[day.weekday()]


def _group_rows(daily_rows: list[SalesRow], grain: Grain) -> list[SalesRow]:
    groups: dict[tuple[str, str], list[SalesRow]] = defaultdict(list)
    for row in daily_rows:
        groups[(_period_of(dt.date.fromisoformat(row.period), grain), row.daypart)].append(row)

    result = []
    for (period, daypart), members in groups.items():
        totals = {field: sum(getattr(member, field) for member in members) for field in AMOUNT_FIELDS}
        if grain == "weekday_daypart":  # 요일 패턴은 평균
            totals = {field: round(value / len(members)) for field, value in totals.items()}
        result.append(SalesRow(period=period, daypart=daypart, days_counted=len(members), **totals))

    def sort_key(row: SalesRow):
        period_key = WEEKDAY_CODES.index(row.period) if grain == "weekday_daypart" else row.period
        return (period_key, DAYPART_ORDER.index(row.daypart))

    return sorted(result, key=sort_key)
