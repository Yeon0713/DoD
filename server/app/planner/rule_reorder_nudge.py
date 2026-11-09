"""매달 단골 재주문 권유 규칙.

매달 오는 단골(MONTHLY)이 불만이 아닌 리뷰를 남기면, 그 리뷰 답글을 올린 토요일에서 4주 뒤 토요일에
다른 리뷰 답글과 같은 때(10:00 승인 요청, 11:00 발송) 리뷰 답글이 아닌 재주문 권유 메시지를 보낸다.
예) "이번 주말 식사로 이건 어떠세요?" 메시지 내용과 실제 발송 채널(네이버 알림 등)은 2차에서 정한다.
"""

import datetime as dt

from app.core.seoul_time import at_time
from app.planner.data_shapes import Basis, CustomerCycle, PlanItem, Review, StoreSettings
from app.planner.notification_time_helpers import slot_at
from app.planner.rule_review_reply import (
    SATURDAY_APPROVAL_SLOT,
    SATURDAY_SEND_TIME,
    classify_review,
    saturday_reply_times,
)

NUDGE_AFTER_WEEKS = 4
REASON_LINE = "한 달에 한 번 오시는 단골 손님이 다시 주문할 때가 됐어요. 재주문 권유 메시지를 보내요."


def plan_reorder_nudges(
    reviews: list[Review], cycles_by_customer: dict[str, CustomerCycle], store: StoreSettings
) -> list[PlanItem]:
    items = []
    for review in reviews:
        if review.label is None or classify_review(review, cycles_by_customer) != "MONTHLY":
            continue
        reply_approval_at, _ = saturday_reply_times(review.written_at, store)
        nudge_saturday = reply_approval_at.date() + dt.timedelta(weeks=NUDGE_AFTER_WEEKS)
        send_at = at_time(nudge_saturday, SATURDAY_SEND_TIME)
        items.append(
            PlanItem(
                plan_id=f"REORDER_NUDGE:{review.customer_key}:{nudge_saturday}",
                task_type="REORDER_NUDGE",
                basis=Basis(kind="CUSTOMER", ref_id=review.customer_key),
                target_date=nudge_saturday,
                approval_request_at=slot_at(nudge_saturday, SATURDAY_APPROVAL_SLOT, store),
                execute_at=send_at,
                deadline_at=send_at,
                reason_line=REASON_LINE,
                planned_at=review.written_at,
            )
        )
    return items
