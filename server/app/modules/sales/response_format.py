"""GET /api/sales 응답 모양."""

from typing import Literal

from pydantic import BaseModel

from app.planner.data_shapes import Daypart

# 묶는 단위: 하루, 한 주(월요일 시작), 한 달, 요일 × 시간대 패턴
Grain = Literal["day", "week", "month", "weekday_daypart"]


class SalesRow(BaseModel):
    period: str  # day: "2026-11-02", week: 그 주 월요일 "2026-11-02", month: "2026-11", weekday_daypart: "MON"
    daypart: Daypart
    days_counted: int  # 이 줄에 합치거나 평균 낸 날 수
    sales_amount: int
    qty: int
    food_cost: int
    labor_cost: int
    profit: int  # 매출 - 메뉴 원가 - 인건비


class SalesResponse(BaseModel):
    is_example: bool  # true 면 contracts/sample_responses 의 예시 데이터
    grain: Grain
    rows: list[SalesRow]  # day, week, month 는 합계, weekday_daypart 는 평균
