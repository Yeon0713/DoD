"""GET /api/calendar 응답 모양."""

from pydantic import BaseModel

from app.planner.data_shapes import CalendarCell


class CalendarResponse(BaseModel):
    is_example: bool  # true 면 contracts/sample_responses 의 예시 데이터
    cells: list[CalendarCell]  # 날짜 × 시간대(점심, 저녁, 야간) 칸
