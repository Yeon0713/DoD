"""GET /api/today 응답 모양."""

import datetime as dt

from pydantic import BaseModel

from app.planner.data_shapes import NotificationBatch


class TodayResponse(BaseModel):
    is_example: bool  # true 면 contracts/sample_responses 의 예시 데이터
    date: dt.date
    batches: list[NotificationBatch]  # 알림 시각별 묶음(시간순). 각 줄은 plan_id 나 notice_id 로 내용을 가리킨다
