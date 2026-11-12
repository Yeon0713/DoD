"""태성 분석 결과 → 계획 엔진 입력(PlanInputs).

- 매장 설정(StoreSettings): DB 가게 정보 + 사장님이 PATCH /api/settings 로 고친 값
- 달력: 분석의 calendar_day 줄을 계획 엔진의 CalendarCell 로. 기준선이 없는 칸(같은 요일 기록이 4주 미만)은
  계획 엔진과 앱이 숫자를 기다리므로 기준선·예상 0원, 비율 1.0 으로 채운다 (신호는 분석이 이미 NORMAL 로 둔다)
- 손님 주문 주기: 매주·매달 단골만 넘긴다 (NONE 손님은 계획 엔진이 쓰지 않는다)
- 매출 이상: 태성 분석에 아직 계산 코드가 없어서 빈 목록이다
"""

import datetime as dt

from app.analysis.result_shapes import CalendarDayRow, CustomerCycleRow, RiskSignalRow
from app.core.error_response import ApiError
from app.planner.data_shapes import (
    CalendarCell,
    CustomerCycle,
    Event,
    Game,
    PlanInputs,
    Review,
    StoreSettings,
)

# 알림을 보낼지 정할 때 쓰는 기본 장사 시간대. 사장님이 설정 화면에서 바꿀 수 있다.
# (매출을 나누는 점심/저녁/밤 경계와는 다르다. 이건 '이 시간엔 바빠서 알림을 보내지 않는다'를 정하는 값이다)
DEFAULT_NOTICE_DAYPARTS = {
    "LUNCH": ("11:00", "13:30"),
    "DINNER": ("17:00", "20:00"),
    "NIGHT": ("20:00", None),  # None 은 마감 시각까지
}
DEFAULT_BUSY_DAYPARTS = ["LUNCH", "DINNER"]


def hhmm(t: dt.time) -> str:
    return t.strftime("%H:%M")


def default_notice_dayparts(open_time: str, close_time: str) -> dict:
    """기본 시간대를 영업시간 안으로 자른다. 자르고 나서 비면 자르지 않은 기본값을 쓴다."""
    dayparts = {}
    for name, (start, end) in DEFAULT_NOTICE_DAYPARTS.items():
        end = end or close_time
        clipped = (max(start, open_time), min(end, close_time))
        dayparts[name] = {"start": clipped[0], "end": clipped[1]} if clipped[0] < clipped[1] else {"start": start, "end": end}
    return dayparts


WEEKDAYS = ("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN")


def summarize_weekly_hours(weekly_hours: dict) -> dict:
    """요일별 장사 시간에서 대표 장사 시간(가장 많은 요일이 쓰는 시간)과 쉬는 날을 뽑는다. 앱의 summarizeWeekly 와 같다.

    계획 엔진은 요일마다 다른 시간을 아직 모르고 대표 시간 하나와 쉬는 날만 쓴다.
    """
    counts: dict[tuple[str, str], int] = {}
    for code in WEEKDAYS:
        day = weekly_hours.get(code)
        if day:
            counts[(day["open"], day["close"])] = counts.get((day["open"], day["close"]), 0) + 1
    if not counts:
        raise ApiError(400, "NO_OPEN_DAY", "일주일 내내 쉬는 날로 저장할 수는 없어요. 여는 요일을 하나 이상 남겨 주세요.")
    open_time, close_time = max(counts, key=counts.get)
    return {
        "open_time": open_time,
        "close_time": close_time,
        "closed_weekdays": [code for code in WEEKDAYS if not weekly_hours.get(code)],
    }


def build_store_settings(store: dict, changes: dict | None = None) -> StoreSettings:
    """DB 가게 정보로 계획 엔진 매장 설정을 만들고, 사장님이 고친 값(changes)을 덮어쓴다."""
    open_time, close_time = hhmm(store["open_time"]), hhmm(store["close_time"])
    if store["close_time"] < store["open_time"]:
        raise ApiError(
            400,
            "OVERNIGHT_STORE_NOT_SUPPORTED",
            f"{store['name']}처럼 자정을 넘겨 영업하는 가게는 아직 알림 계획을 만들 수 없어요. "
            "달력, 매출, 리뷰, 알바는 볼 수 있어요.",
        )
    opening, afternoon, closing = store["slots"]
    base = {
        "store_id": store["store_id"],
        "name": store["name"],
        "category": store["category"],
        "lat": store["lat"],
        "lng": store["lng"],
        "open_time": open_time,
        "close_time": close_time,
        "dayparts": default_notice_dayparts(open_time, close_time),
        "busy_dayparts": DEFAULT_BUSY_DAYPARTS,
        "slots": {"OPENING": opening, "AFTERNOON": afternoon, "CLOSING": closing},
        "closed_weekdays": store["closed_weekdays"] or [],
    }
    merged = {**base, **(changes or {})}
    if merged.get("weekly_hours"):
        # 사장님이 고친 요일별 시간이 있으면 대표 장사 시간과 쉬는 날을 거기서 다시 뽑는다
        merged.update(summarize_weekly_hours(merged["weekly_hours"]))
        if any(day and day["close"] <= day["open"] for day in merged["weekly_hours"].values()):
            raise ApiError(
                400,
                "OVERNIGHT_STORE_NOT_SUPPORTED",
                "자정을 넘겨 여는 시간은 아직 저장할 수 없어요. 닫는 시각을 여는 시각보다 늦게 적어 주세요.",
            )
    return StoreSettings.model_validate(merged)


def to_calendar_cell(row: CalendarDayRow) -> CalendarCell:
    data = row.model_dump()
    if row.baseline_sales is None:
        data.update(baseline_sales=0, expected_sales=0, ratio=1.0)
    # 그 요일·시간대에 판 적이 없으면(예: 주말엔 점심만 여는 가게의 주말 저녁) 기준은 0 이고 예상·비율은 비어 온다
    if data["expected_sales"] is None:
        data["expected_sales"] = data["baseline_sales"]
    if data["ratio"] is None:
        data["ratio"] = 1.0
    return CalendarCell.model_validate(data)


def to_customer_cycles(rows: list[CustomerCycleRow]) -> list[CustomerCycle]:
    return [CustomerCycle.model_validate(row.model_dump()) for row in rows if row.cycle != "NONE"]


def build_plan_inputs(
    settings: StoreSettings,
    reviews: list[Review],
    customer_cycles: list[CustomerCycleRow],
    calendar_cells: list[CalendarCell],
    risk_signals: list[RiskSignalRow],
    events: list[Event],
    games: list[Game],
) -> PlanInputs:
    return PlanInputs(
        store=settings,
        reviews=reviews,
        customer_cycles=to_customer_cycles(customer_cycles),
        calendar=calendar_cells,
        risk_signals=risk_signals,
        sales_anomalies=[],  # 태성 분석에 매출 이상 계산이 생기면 여기에 넣는다
        events=events,
        games=games,
    )
