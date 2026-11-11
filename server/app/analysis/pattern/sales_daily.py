"""하루 × 시간대 매출(sales_daily)을 만든다.

- now 이전 주문만 쓰고, 마감 시각이 지난 날만 만든다. 첫 주문 날부터 마지막 주문 날까지 휴무일을 빼고
  날마다 모든 시간대 칸을 만든다(주문이 없으면 0). 마지막 주문 날 뒤는 데이터가 안 들어온 날과
  손님이 없던 날을 구별할 수 없어서 만들지 않는다.
- 빠지는 항목은 데이터가 있을 때만 채운다.
  - 메뉴 원가: 그 칸에 팔린 메뉴의 원가가 모두 있을 때만 수량 × 원가. 하나라도 없거나, 메뉴 원가 데이터가 아예 없으면 None
  - 인건비: 근무 시간 중 그 시간대와 겹친 시간 × 시급. 근무표가 비어 있으면 None
  - 배달앱 수수료, 배달비, 결제수수료: 지금은 가져올 데이터가 없어서 None
- 영업시간 밖 주문은 칸에 넣지 않고 건수만 센다.
"""

import datetime as dt
from collections import defaultdict
from dataclasses import dataclass

from app.analysis.input_shapes import AnalysisInputs, DaypartRange, require_aware
from app.analysis.pattern.daypart_time import (
    daypart_at,
    dayparts_of,
    is_closed_day,
    is_day_finished,
    overlap_minutes,
    window,
)
from app.analysis.result_shapes import SalesDailyRow
from app.core.seoul_time import to_seoul


@dataclass
class SalesDailyResult:
    rows: list[SalesDailyRow]
    outside_order_count: int  # 영업시간(시간대) 밖이라 칸에 넣지 않은 주문 수


def build_sales_daily(inputs: AnalysisInputs, now: dt.datetime) -> SalesDailyResult:
    require_aware(now)
    store = inputs.store
    ranges = dayparts_of(store)
    orders = [order for order in inputs.orders if order.ordered_at <= now]
    if not orders:
        return SalesDailyResult(rows=[], outside_order_count=0)

    items_by_order = defaultdict(list)
    for item in inputs.order_items:
        items_by_order[item.order_id].append(item)
    unit_cost = {menu.menu_id: menu.unit_cost for menu in inputs.menus}
    has_cost_data = any(menu.unit_cost is not None for menu in inputs.menus)  # 원가 데이터가 아예 없으면 모든 칸이 None

    sales = defaultdict(int)
    qty = defaultdict(int)
    food_cost = defaultdict(int)
    cost_missing = set()  # 원가를 모르는 메뉴가 팔린 칸
    outside = 0
    for order in orders:
        daypart = daypart_at(order.ordered_at, ranges)
        if daypart is None:
            outside += 1
            continue
        key = (to_seoul(order.ordered_at).date(), daypart)
        sales[key] += order.total_amount
        for item in items_by_order[order.order_id]:
            qty[key] += item.quantity
            cost = unit_cost.get(item.menu_id)
            if cost is None:
                cost_missing.add(key)
            else:
                food_cost[key] += cost * item.quantity

    order_days = [to_seoul(order.ordered_at).date() for order in orders]
    last_day = max(order_days)
    rows = []
    day = min(order_days)
    while day <= last_day and is_day_finished(day, store, now):
        if not is_closed_day(day, store):
            for r in ranges:
                key = (day, r.daypart)
                labor = _labor_cost(inputs, day, r) if inputs.shifts else None
                food = food_cost[key] if has_cost_data and key not in cost_missing else None
                deductions = [value for value in (food, labor) if value is not None]
                rows.append(
                    SalesDailyRow(
                        date=day,
                        daypart=r.daypart,
                        sales_amount=sales[key],
                        qty=qty[key],
                        food_cost=food,
                        labor_cost=labor,
                        profit=sales[key] - sum(deductions),
                    )
                )
        day += dt.timedelta(days=1)
    return SalesDailyResult(rows=rows, outside_order_count=outside)


def _labor_cost(inputs: AnalysisInputs, day: dt.date, r: DaypartRange) -> int:
    """그 날 그 시간대와 겹친 근무 시간 × 시급의 합(원 단위 반올림)."""
    start, end = window(day, r)
    total = 0.0
    for shift in inputs.shifts:
        minutes = overlap_minutes(shift.starts_at, shift.ends_at, start, end)
        total += minutes / 60 * shift.hourly_wage
    return round(total)
