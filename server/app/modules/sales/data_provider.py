"""매출 패턴 데이터 가져오기 (GET /api/sales?grain=...).

DB → 태성 분석(sales_daily, 하루 × 시간대, 마감이 지난 날만)을 요청한 단위(week, month, weekday_daypart)로 묶는다.
매출 탭 화면 6개는 dashboard_data_provider.py 에 있다.
"""

import datetime as dt
from collections import defaultdict

from app.core.seoul_time import is_within_dates
from app.data_pipeline.store_snapshot_cache import get_snapshot
from app.modules.sales.response_format import Grain, SalesResponse, SalesRow

AMOUNT_FIELDS = ("sales_amount", "qty", "food_cost", "labor_cost", "profit")
WEEKDAY_CODES = ("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN")
DAYPART_ORDER = ("LUNCH", "DINNER", "NIGHT")


def get_sales(store_id: str, from_date: dt.date | None, to_date: dt.date | None, grain: Grain) -> SalesResponse:
    snapshot = get_snapshot(store_id)
    rows = [
        SalesRow(
            period=row.date.isoformat(),
            daypart=row.daypart,
            days_counted=1,
            sales_amount=row.sales_amount,
            qty=row.qty,
            food_cost=row.food_cost,
            labor_cost=row.labor_cost,
            profit=row.profit,
        )
        for row in snapshot.sales_daily
        if is_within_dates(row.date, from_date, to_date)
    ]
    return SalesResponse(is_example=False, grain=grain, rows=_group_rows(rows, grain))


def _period_of(day: dt.date, grain: Grain) -> str:
    if grain == "day":
        return day.isoformat()
    if grain == "week":
        return (day - dt.timedelta(days=day.weekday())).isoformat()
    if grain == "month":
        return day.strftime("%Y-%m")
    return WEEKDAY_CODES[day.weekday()]


def _sum(values: list[int | None]) -> int | None:
    """하나라도 값이 없으면(데이터가 없는 항목) 합도 없다."""
    return None if any(v is None for v in values) else sum(values)


def _group_rows(daily_rows: list[SalesRow], grain: Grain) -> list[SalesRow]:
    groups: dict[tuple[str, str], list[SalesRow]] = defaultdict(list)
    for row in daily_rows:
        groups[(_period_of(dt.date.fromisoformat(row.period), grain), row.daypart)].append(row)

    result = []
    for (period, daypart), members in groups.items():
        totals = {field: _sum([getattr(member, field) for member in members]) for field in AMOUNT_FIELDS}
        if grain == "weekday_daypart":  # 요일 패턴은 평균
            totals = {field: None if value is None else round(value / len(members)) for field, value in totals.items()}
        result.append(SalesRow(period=period, daypart=daypart, days_counted=len(members), **totals))

    def sort_key(row: SalesRow):
        period_key = WEEKDAY_CODES.index(row.period) if grain == "weekday_daypart" else row.period
        return (period_key, DAYPART_ORDER.index(row.daypart))

    return sorted(result, key=sort_key)
