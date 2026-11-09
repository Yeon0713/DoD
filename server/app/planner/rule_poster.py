"""③ 포스터 규칙.

- 달력에서 수요 신호 HIGH 를 만든 행사와 경기마다 시작일을 D로 둔다.
  과거 효과가 없어 태그가 붙지 않은 행사·경기(예: 11/18 야구 경기)는 포스터를 만들지 않는다.
- 행사·경기가 없는 주말은 그 주 토요일을 D로 두고 주말 포스터를 만든다.
  주말에 행사·경기가 있으면 주말 포스터는 따로 만들지 않는다.
- D-3 14:00 승인 요청, D-2 출근 후 게시.
  기한은 행사·경기 시작 시각, 주말 포스터는 토요일 영업 시작 시각.
"""

import datetime as dt

from app.core.seoul_time import at_time
from app.planner.data_shapes import Basis, CalendarCell, Event, Game, PlanItem, StoreSettings
from app.planner.notification_time_helpers import KOREAN_WEEKDAYS, postpone_if_passed, saturday_of_week, slot_at

POSTER_TAGS = ("EVENT", "GAME")


def _is_high_with_schedule(cell: CalendarCell) -> bool:
    return cell.signal == "HIGH" and any(reason.tag in POSTER_TAGS for reason in cell.reasons)


def _poster_item(
    ref_id: str, kind: str, title: str, start_at: dt.datetime, known_at: dt.datetime, store: StoreSettings
) -> PlanItem:
    day = start_at.date()
    return PlanItem(
        plan_id=f"POSTER:{ref_id}:{day}",
        task_type="POSTER",
        basis=Basis(kind=kind, ref_id=ref_id),
        target_date=day,
        approval_request_at=postpone_if_passed(
            slot_at(day - dt.timedelta(days=3), "AFTERNOON", store), known_at, store
        ),
        execute_at=slot_at(day - dt.timedelta(days=2), "OPENING", store),
        deadline_at=start_at,
        reason_line=f"{KOREAN_WEEKDAYS[day.weekday()]} {title} 홍보 포스터를 올려요.",
        planned_at=known_at,
    )


def plan_posters(
    calendar: list[CalendarCell], events: list[Event], games: list[Game], store: StoreSettings
) -> list[PlanItem]:
    schedules = {event.event_id: ("EVENT", event.title, event.start_at) for event in events}
    schedules |= {game.game_id: ("GAME", game.title, game.start_at) for game in games}

    # HIGH 신호를 만든 행사·경기와, 그걸 알게 된 시각
    known_at_by_ref: dict[str, dt.datetime] = {}
    for cell in calendar:
        if cell.signal != "HIGH":
            continue
        for reason in cell.reasons:
            if reason.tag in POSTER_TAGS and reason.ref_id in schedules:
                previous = known_at_by_ref.get(reason.ref_id, cell.computed_at)
                known_at_by_ref[reason.ref_id] = max(previous, cell.computed_at)

    items = []
    for ref_id in sorted(known_at_by_ref):
        kind, title, start_at = schedules[ref_id]
        items.append(_poster_item(ref_id, kind, title, start_at, known_at_by_ref[ref_id], store))

    # 행사·경기가 없는 주말의 포스터
    weekends_with_schedule = {
        saturday_of_week(cell.date)
        for cell in calendar
        if cell.date.weekday() >= 5 and _is_high_with_schedule(cell)
    }
    for saturday in sorted({cell.date for cell in calendar if cell.date.weekday() == 5}):
        if saturday in weekends_with_schedule:
            continue
        known_at = max(cell.computed_at for cell in calendar if cell.date == saturday)
        items.append(
            PlanItem(
                plan_id=f"POSTER:{saturday}:{saturday}",
                task_type="POSTER",
                basis=Basis(kind="CALENDAR_DAY", ref_id=str(saturday)),
                target_date=saturday,
                approval_request_at=postpone_if_passed(
                    slot_at(saturday - dt.timedelta(days=3), "AFTERNOON", store), known_at, store
                ),
                execute_at=slot_at(saturday - dt.timedelta(days=2), "OPENING", store),
                deadline_at=at_time(saturday, store.open_time),
                reason_line="이번 주말 손님을 부르는 포스터를 올려요.",
                planned_at=known_at,
            )
        )
    return items
