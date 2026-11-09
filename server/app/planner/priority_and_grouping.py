"""할 일과 알림을 알림 시각별로 묶고 우선순위대로 줄 세운다.

- 우선순위: 1 불만 리뷰 답글, 2 반복 불만 개선, 3 다음 날 실행할 일의 승인 요청,
  4 그 밖(오늘 실행 알림, 예고, 매출 이상, 토요일 답글·재주문 권유 승인 요청 포함)
- 같은 우선순위 안에서는 기한이 빠른 것이 앞이다.
- 항목이 없는 알림 시각에는 묶음을 만들지 않는다.
"""

import datetime as dt
from collections import defaultdict

from app.core.seoul_time import to_seoul
from app.planner.data_shapes import BatchEntry, NoticeItem, NotificationBatch, PlanItem, Priority, StoreSettings
from app.planner.notification_time_helpers import slot_name_of


def approval_priority(item: PlanItem) -> Priority:
    if item.task_type == "REVISIT_REPLY" and item.revisit_class == "QUICK":
        return 1
    if item.task_type == "REVIEW_FIX":
        return 2
    if item.execute_at is not None:
        approval_day = to_seoul(item.approval_request_at).date()
        if to_seoul(item.execute_at).date() == approval_day + dt.timedelta(days=1):
            return 3
    return 4


def needs_execute_reminder(item: PlanItem, store: StoreSettings) -> bool:
    """실행 시각이 따로 있고 그게 알림 가능 시각이면 실행 알림을 보낸다.

    불만 리뷰 답글은 승인 요청 하나로 승인과 실행을 함께 하고,
    토요일 11:00 답글·재주문 권유는 승인 뒤 자동으로 올라가서 실행 알림을 따로 보내지 않는다.
    """
    return (
        item.execute_at is not None
        and item.execute_at != item.approval_request_at
        and slot_name_of(item.execute_at, store) is not None
    )


def group_into_batches(
    plan_items: list[PlanItem], notice_items: list[NoticeItem], store: StoreSettings
) -> list[NotificationBatch]:
    # 알림 시각 → [(우선순위, 기한, id, 한 줄)]
    rows_by_time: dict[dt.datetime, list[tuple]] = defaultdict(list)

    for item in plan_items:
        priority = approval_priority(item)
        entry = BatchEntry(plan_id=item.plan_id, notify_kind="APPROVAL_REQUEST", priority=priority)
        rows_by_time[item.approval_request_at].append((priority, item.deadline_at, item.plan_id, entry))
        if needs_execute_reminder(item, store):
            entry = BatchEntry(plan_id=item.plan_id, notify_kind="EXECUTE_REMINDER", priority=4)
            rows_by_time[item.execute_at].append((4, item.deadline_at, item.plan_id, entry))

    for notice in notice_items:
        kind = "PREVIEW" if notice.kind == "WEEKLY_PREVIEW" else "NOTICE"
        entry = BatchEntry(notice_id=notice.notice_id, notify_kind=kind, priority=4)
        rows_by_time[notice.slot_at].append((4, None, notice.notice_id, entry))

    batches = []
    for slot_time in sorted(rows_by_time):
        slot = slot_name_of(slot_time, store)
        if slot is None:
            raise ValueError(f"{slot_time} 은 알림 가능 시각이 아닙니다.")
        # 우선순위 → 기한(없으면 맨 뒤) → id 순서
        rows = sorted(rows_by_time[slot_time], key=lambda r: (r[0], r[1] is None, r[1] or slot_time, r[2]))
        batches.append(NotificationBatch(slot_at=slot_time, slot=slot, entries=[row[3] for row in rows]))
    return batches
