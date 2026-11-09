"""① 리뷰 답글 시각 규칙.

- 불만 리뷰(QUICK): 리뷰 뒤 첫 알림 시각에 답글 승인을 요청하고 바로 올린다. 기한은 그날 마감.
- 그 밖의 리뷰(매주 단골 WEEKLY, 매달 단골 MONTHLY, 일반 BASIC):
  리뷰가 달린 주의 토요일 10:00(출근 후)에 답글과 함께 승인을 요청하고, 승인되면 11:00 에 올린다.
  그 토요일 10:00 승인 요청이 이미 지난 뒤(토요일 10시 이후, 일요일)에 달린 리뷰는 다음 주 토요일로 넘긴다.
"""

import datetime as dt

from app.core.seoul_time import at_time, to_seoul
from app.planner.data_shapes import Basis, CustomerCycle, PlanItem, RevisitClass, Review, StoreSettings
from app.planner.notification_time_helpers import close_time_on, next_slot, saturday_of_week, slot_at

SATURDAY_APPROVAL_SLOT = "OPENING"  # 토요일 답글 승인 요청: 출근 후(10:00)
SATURDAY_SEND_TIME = "11:00"  # 승인된 답글을 올리는 시각

REASON_LINES = {
    "QUICK": "불만이 담긴 리뷰예요. 빨리 답글을 달아 주세요.",
    "WEEKLY": "매주 오시는 단골 손님의 리뷰예요. 토요일 11시에 답글을 올려요.",
    "MONTHLY": "한 달에 한 번 오시는 단골 손님의 리뷰예요. 토요일 11시에 답글을 올려요.",
    "BASIC": "이번 주에 들어온 리뷰예요. 토요일 11시에 답글을 함께 올려요.",
}


def classify_review(review: Review, cycles_by_customer: dict[str, CustomerCycle]) -> RevisitClass:
    """불만 → 매주 단골 → 매달 단골 → 일반 순서로 판단한다."""
    if review.label is not None and review.label.is_quick:
        return "QUICK"
    cycle = cycles_by_customer.get(review.customer_key) if review.customer_key else None
    if cycle is not None and cycle.cycle == "WEEKLY":
        return "WEEKLY"
    if cycle is not None and cycle.cycle == "MONTHLY":
        return "MONTHLY"
    return "BASIC"


def saturday_reply_times(written_at: dt.datetime, store: StoreSettings) -> tuple[dt.datetime, dt.datetime]:
    """불만이 아닌 리뷰의 (승인 요청 시각, 답글 올리는 시각). 예) 11/17 리뷰 → (11/21 10:00, 11/21 11:00)"""
    saturday = saturday_of_week(to_seoul(written_at).date())
    approval_at = slot_at(saturday, SATURDAY_APPROVAL_SLOT, store)
    if written_at >= approval_at:
        saturday += dt.timedelta(days=7)
        approval_at = slot_at(saturday, SATURDAY_APPROVAL_SLOT, store)
    return approval_at, at_time(saturday, SATURDAY_SEND_TIME)


def plan_review_replies(
    reviews: list[Review], cycles_by_customer: dict[str, CustomerCycle], store: StoreSettings
) -> list[PlanItem]:
    items = []
    for review in reviews:
        if review.label is None:  # 분류 전 리뷰는 분류된 뒤 다음 계산에서 다룬다
            continue
        revisit_class = classify_review(review, cycles_by_customer)
        if revisit_class == "QUICK":
            approval_at = next_slot(review.written_at, store)
            execute_at = approval_at  # 승인 요청 하나로 승인과 실행을 함께 한다
            deadline_at = close_time_on(approval_at.date(), store)
        else:
            approval_at, execute_at = saturday_reply_times(review.written_at, store)
            deadline_at = execute_at
        target_date = execute_at.date()
        items.append(
            PlanItem(
                plan_id=f"REVISIT_REPLY:{review.review_id}:{target_date}",
                task_type="REVISIT_REPLY",
                revisit_class=revisit_class,
                basis=Basis(kind="REVIEW", ref_id=review.review_id),
                target_date=target_date,
                approval_request_at=approval_at,
                execute_at=execute_at,
                deadline_at=deadline_at,
                reason_line=REASON_LINES[revisit_class],
                planned_at=review.written_at,
            )
        )
    return items
