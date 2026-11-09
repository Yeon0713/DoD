"""할 일 목록 데이터 가져오기.

지금은 응답 예시(plan_response.example.json)에서 기간에 맞는 것만 골라 돌려준다.
- 할 일: 승인 요청 시각이나 실행 시각이 기간 안에 있는 것
- 알림: 알림 시각이 기간 안에 있는 것
계획 엔진을 연결하면 make_plan 결과에서 같은 방식으로 고른다.
"""

import datetime as dt

from app.core.sample_response_loader import load_sample_response
from app.core.seoul_time import is_within_dates, to_seoul
from app.modules.plan.response_format import PlanResponse


def get_plan(from_date: dt.date | None, to_date: dt.date | None) -> PlanResponse:
    plan = PlanResponse.model_validate(load_sample_response("plan"))
    plan_items = [
        item
        for item in plan.plan_items
        if any(
            t is not None and is_within_dates(to_seoul(t).date(), from_date, to_date)
            for t in (item.approval_request_at, item.execute_at)
        )
    ]
    notice_items = [
        notice
        for notice in plan.notice_items
        if is_within_dates(to_seoul(notice.slot_at).date(), from_date, to_date)
    ]
    return plan.model_copy(update={"plan_items": plan_items, "notice_items": notice_items})
