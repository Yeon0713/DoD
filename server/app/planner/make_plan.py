"""계획 엔진 입구. 분석 결과를 받아 할 일, 승인 없는 알림, 알림 묶음을 만든다.

now 에는 '지금'을 넣는다. now 이전에 생긴 데이터(리뷰, 위험 신호, 매출 이상, 계산된 달력과 손님 주기)만 쓰고,
행사·경기 일정은 앞날 것도 그대로 쓴다. 테스트에서는 원하는 시각을 넣어 그 시점의 계획을 확인한다.
"""

import datetime as dt

from app.planner.data_shapes import PlanInputs, PlanResult
from app.planner.info_alerts import make_sales_anomaly_alerts, make_weekly_previews
from app.planner.notification_time_helpers import off_closed_day
from app.planner.priority_and_grouping import group_into_batches
from app.planner.rule_complaint_fix import plan_complaint_fixes
from app.planner.rule_menu_order import plan_menu_orders
from app.planner.rule_poster import plan_posters
from app.planner.rule_reorder_nudge import plan_reorder_nudges
from app.planner.rule_review_reply import plan_review_replies


def make_plan(inputs: PlanInputs, now: dt.datetime) -> PlanResult:
    store = inputs.store

    # now 시점에 알 수 있는 데이터만
    reviews = [review for review in inputs.reviews if review.written_at <= now]
    cycles = {cycle.customer_key: cycle for cycle in inputs.customer_cycles if cycle.computed_at <= now}
    calendar = [cell for cell in inputs.calendar if cell.computed_at <= now]
    risks = [risk for risk in inputs.risk_signals if risk.detected_at <= now]
    anomalies = [anomaly for anomaly in inputs.sales_anomalies if anomaly.detected_at <= now]

    plan_items = [
        *plan_review_replies(reviews, cycles, store),
        *plan_reorder_nudges(reviews, cycles, store),
        *plan_menu_orders(calendar, store),
        *plan_posters(calendar, inputs.events, inputs.games, store),
        *plan_complaint_fixes(risks, store),
    ]
    # 쉬는 날로 잡힌 승인 요청과 실행 시각은 그 뒤 처음 여는 날로 옮긴다 (쉬는 날에는 알림이 가지 않는다)
    plan_items = [
        item.model_copy(
            update={
                "approval_request_at": off_closed_day(item.approval_request_at, store),
                "execute_at": off_closed_day(item.execute_at, store),
            }
        )
        for item in plan_items
    ]
    # 같은 plan_id 는 하나만 남긴다
    plan_items = sorted(
        {item.plan_id: item for item in plan_items}.values(),
        key=lambda item: (item.approval_request_at, item.plan_id),
    )

    notice_items = sorted(
        [
            notice.model_copy(update={"slot_at": off_closed_day(notice.slot_at, store)})
            for notice in (
                *make_weekly_previews(calendar, inputs.events, inputs.games, plan_items, store),
                *make_sales_anomaly_alerts(anomalies, store),
            )
        ],
        key=lambda notice: (notice.slot_at, notice.notice_id),
    )

    return PlanResult(
        plan_items=plan_items,
        notice_items=notice_items,
        batches=group_into_batches(plan_items, notice_items, store),
    )
