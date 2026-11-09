"""GET /api/plan 응답 모양."""

from pydantic import BaseModel

from app.planner.data_shapes import NoticeItem, PlanItem


class PlanResponse(BaseModel):
    is_example: bool  # true 면 contracts/sample_responses 의 예시 데이터
    plan_items: list[PlanItem]  # 할 일 (승인 요청 시각 순)
    notice_items: list[NoticeItem]  # 승인 없는 알림 (월요일 주간 예고, 매출 이상)
