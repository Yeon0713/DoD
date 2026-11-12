"""② 메뉴판 바꾸기 규칙.

날짜 D의 달력 이유 태그(행사, 경기, 계절) 묶음이 전날과 다르면 메뉴판을 바꾼다.
행사가 끝나 원래대로 돌아가는 날도 포함한다.
날씨는 하루 단위로 생겼다 사라져 교체와 되돌리기가 연달아 생기기 쉬우므로 메뉴판 규칙에서만 뺀다
(달력의 날씨 이유와 예상 매출은 그대로다).
D-1 14:00 승인 요청, D 출근 후 실행, 기한은 D 마감.
쉬는 날은 건너뛴다: 쉬는 날에는 바꾸지 않고, 쉬는 날 다음 날은 그 앞의 여는 날과 태그를 견준다.
(승인 요청이 쉬는 날에 걸리면 make_plan 이 다음 여는 날로 옮긴다.)
"""

import datetime as dt
from collections import defaultdict

from app.planner.data_shapes import Basis, CalendarCell, PlanItem, StoreSettings
from app.planner.notification_time_helpers import close_time_on, is_closed_day, postpone_if_passed, slot_at

TAG_NAMES = {"EVENT": "근처 행사", "GAME": "경기", "SEASON": "계절 변화"}


def tags_by_date(calendar: list[CalendarCell]) -> dict[dt.date, frozenset[tuple[str, str]]]:
    """날짜별 (태그, 근거 id) 묶음. 시간대 세 칸의 태그를 합친다.

    날씨 태그는 뺀다. 날씨만 있던 날도 빈 묶음으로 남겨 다음 날의 비교 대상이 된다.
    """
    tags = defaultdict(set)
    for cell in calendar:
        tags[cell.date] |= {(reason.tag, reason.ref_id) for reason in cell.reasons if reason.tag != "WEATHER"}
    return {day: frozenset(day_tags) for day, day_tags in tags.items()}


def _reason_line(added: set[tuple[str, str]], removed: set[tuple[str, str]]) -> str:
    if added:
        names = ", ".join(sorted({TAG_NAMES[tag] for tag, _ in added}))
        return f"{names} 때문에 메뉴판 순서를 바꿔요."
    names = ", ".join(sorted({TAG_NAMES[tag] for tag, _ in removed}))
    return f"{names} 기간이 끝나 메뉴판 순서를 되돌려요."


def plan_menu_orders(calendar: list[CalendarCell], store: StoreSettings) -> list[PlanItem]:
    tags = tags_by_date(calendar)
    computed_at = defaultdict(list)
    for cell in calendar:
        computed_at[cell.date].append(cell.computed_at)

    items = []
    for day in sorted(tags):
        if is_closed_day(day, store):
            continue
        yesterday = day - dt.timedelta(days=1)
        previous = yesterday
        while is_closed_day(previous, store) and (day - previous).days < 7:
            previous -= dt.timedelta(days=1)
        if previous not in tags or tags[day] == tags[previous]:
            continue
        known_at = max(computed_at[day] + computed_at[previous])
        approval_at = postpone_if_passed(slot_at(yesterday, "AFTERNOON", store), known_at, store)
        items.append(
            PlanItem(
                plan_id=f"MENU_ORDER:{day}:{day}",
                task_type="MENU_ORDER",
                basis=Basis(kind="CALENDAR_DAY", ref_id=str(day)),
                target_date=day,
                approval_request_at=approval_at,
                execute_at=slot_at(day, "OPENING", store),
                deadline_at=close_time_on(day, store),
                reason_line=_reason_line(tags[day] - tags[previous], tags[previous] - tags[day]),
                planned_at=known_at,
            )
        )
    return items
