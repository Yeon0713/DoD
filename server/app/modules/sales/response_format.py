"""GET /api/sales 응답 모양. 매출 탭 화면 6개의 모양은 dashboard_response_format.py 에 있다."""

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
    food_cost: int | None  # 메뉴 원가 합. DB 에 메뉴 원가가 없으면 None
    labor_cost: int | None  # 인건비. 근무 기록이 없으면 None
    profit: int  # 매출 - 값이 있는 빠지는 항목(원가, 인건비 등)의 합


class SalesResponse(BaseModel):
    is_example: bool  # true 면 contracts/sample_responses 의 예시 데이터
    grain: Grain
    rows: list[SalesRow]  # day, week, month 는 합계, weekday_daypart 는 평균
