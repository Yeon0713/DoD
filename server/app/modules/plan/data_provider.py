"""할 일 목록 데이터 가져오기.

DB → 태성 분석 → 계획 엔진 결과(store_snapshot_cache)에서 기간에 맞는 것만 골라 돌려준다.
- 할 일: 승인 요청 시각이나 실행 시각이 기간 안에 있는 것
- 알림: 알림 시각이 기간 안에 있는 것
카드 문구(reason_line)와 알림 글(text)은 CLOVA X 로 다듬은 문장이 있으면 그것으로 바꿔 보낸다.
리뷰 답글·재주문 인사에는 CLOVA X 가 쓴 초안(draft_text)을 싣는다 (review_reply_writer).
"""

import datetime as dt

from app.core.seoul_time import is_within_dates, to_seoul
from app.data_pipeline.store_snapshot_cache import get_snapshot
from app.modules.plan.response_format import PlanItemForScreen, PlanResponse
from app.sentence_polish.polish_with_clova import polished


def get_plan(store_id: str, from_date: dt.date | None, to_date: dt.date | None) -> PlanResponse:
    snapshot = get_snapshot(store_id)
    plan = snapshot.require_plan()
    store = snapshot.store
    plan_items = [
        PlanItemForScreen(
            **item.model_dump(),
            draft_text=snapshot.draft_texts.get(item.plan_id),
        ).model_copy(update={"reason_line": polished("plan_card", item.reason_line, store)})
        for item in plan.plan_items
        if any(
            t is not None and is_within_dates(to_seoul(t).date(), from_date, to_date)
            for t in (item.approval_request_at, item.execute_at)
        )
    ]
    notice_items = [
        notice.model_copy(update={"text": polished("notice", notice.text, store)})
        for notice in plan.notice_items
        if is_within_dates(to_seoul(notice.slot_at).date(), from_date, to_date)
    ]
    return PlanResponse(is_example=False, plan_items=plan_items, notice_items=notice_items)
