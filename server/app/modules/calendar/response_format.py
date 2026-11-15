"""GET /api/calendar 응답 모양."""

from pydantic import BaseModel

from app.planner.data_shapes import CalendarCell


class CalendarResponse(BaseModel):
    is_example: bool  # true 면 contracts/sample_responses 의 예시 데이터
    cells: list[CalendarCell]  # 날짜 × 시간대(점심, 저녁, 야간) 칸
    # 칸의 이유에 나온 행사·경기 이름 (ref_id → 이름). 예) {"event_9002": "남양 가을 축제"}
    # 이유 한 줄(reason_text)은 CLOVA 가 다듬어 바뀔 수 있어서, 카드(포스터 등)가 행사 이름을 쓰려면 이것을 본다
    names: dict[str, str] = {}
