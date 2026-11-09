"""② 메뉴판 바꾸기 규칙.

날짜 D의 달력 이유 태그(행사, 경기, 날씨, 계절) 묶음이 전날과 다르면 메뉴판을 바꾼다.
행사가 끝나 원래대로 돌아가는 날도 포함한다.
D-1 14:00 승인 요청, D 출근 후 실행, 기한은 D 마감.
"""

import datetime as dt
from collections import defaultdict

from app.planner.data_shapes import Basis, CalendarCell, PlanItem, StoreSettings
from app.planner.notification_time_helpers import close_time_on, postpone_if_passed, slot_at

TAG_NAMES = {"EVENT": "근처 행사", "GAME": "경기", "WEATHER": "날씨 변화", "SEASON": "계절 변화"}


def tags_by_date(calendar: list[CalendarCell]) -> dict[dt.date, frozenset[tuple[str, str]]]:
    """날짜별 (태그, 근거 id) 묶음. 시간대 세 칸의 태그를 합친다."""
    tags = defaultdict(set)
    for cell in calendar:
        tags[cell.date] |= {(reason.tag, reason.ref_id) for reason in cell.reasons}
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
        previous = day - dt.timedelta(days=1)
        if previous not in tags or tags[day] == tags[previous]:
            continue
        known_at = max(computed_at[day] + computed_at[previous])
        approval_at = postpone_if_passed(slot_at(previous, "AFTERNOON", store), known_at, store)
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
