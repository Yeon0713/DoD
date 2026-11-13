"""② 메뉴판 바꾸기 규칙.

날짜 D의 달력 이유 태그(행사, 경기, 계절) 묶음이 전날과 다르면 메뉴판을 바꾼다.
행사가 끝나 원래대로 돌아가는 날도 포함한다.
날씨는 하루 단위로 생겼다 사라져 교체와 되돌리기가 연달아 생기기 쉬우므로 메뉴판 규칙에서만 뺀다
(달력의 날씨 이유와 예상 매출은 그대로다).
D-1 14:00 승인 요청, D 출근 후 실행, 기한은 D 마감.
쉬는 날은 건너뛴다: 쉬는 날에는 바꾸지 않고, 쉬는 날 다음 날은 그 앞의 여는 날과 태그를 견준다.
(승인 요청이 쉬는 날에 걸리면 make_plan 이 다음 여는 날로 옮긴다.)

메뉴판 기준 태그(menu_board_bases)는 날짜별로 메뉴판을 어떤 태그에 맞춰 둘지 정한다. 교체 이득이 교체 부담보다
큰 태그만 바꿀 만하다고 본다. 위 카드 가운데 기준 태그가 직전 영업일과 같은 카드는 바뀌는 것이 없다
(unchanged_menu_orders).
"""

import datetime as dt
from collections import defaultdict
from dataclasses import dataclass

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


# ── 메뉴판 기준 태그 ──

COST_PER_MENU = 0.1  # 메뉴 1개를 움직이는 교체 부담. 효과 단위(0.10 = 10%)이고 매출액이 아니다
_EPSILON = 1e-9  # 효과 평균의 부동소수 오차. 이득이 부담과 같으면 바꾸지 않는다
_DIGITS = 9  # 하루 효과를 견줄 때 남기는 소수 자리. 칸 수가 달라도 같은 효과는 같게 본다


@dataclass(frozen=True)
class TagPeriod:
    """근거 id 하나의 원본 일정(양 끝 포함). 행사는 시작~끝, 경기는 당일, 계절은 시작~끝.

    end 가 None 이면 아직 끝나지 않았다(계절). ref_id 는 달력 이유의 근거 id 와 같은 값이다.
    """

    ref_id: str
    start: dt.date
    end: dt.date | None = None


def _switch_benefit(effects: list[float], open_days: int) -> float:
    """교체 이득 = 대표 |effect|(평균) × 기간 안의 영업일 수. 교체 여부를 정하는 점수이고 매출액이 아니다."""
    return _strength(effects) * open_days


def _strength(effects: list[float]) -> float:
    """대표 |effect|: 그 근거 id가 붙은 달력 칸들의 |effect| 평균(하루 효과)."""
    return round(sum(abs(effect) for effect in effects) / len(effects), _DIGITS)


def _open_days(start: dt.date, end: dt.date, store: StoreSettings) -> int:
    """start~end(양 끝 포함)의 영업일 수. 휴무일은 기간을 끊지 않고 세지만 않는다."""
    days, day = 0, start
    while day <= end:
        days += not is_closed_day(day, store)
        day += dt.timedelta(days=1)
    return days


def tag_periods(calendar: list[CalendarCell], periods: list[TagPeriod]) -> dict[str, tuple[dt.date, dt.date]]:
    """달력에 보인 근거 id(날씨 제외)마다 (첫날, 끝날). 양 끝 포함.

    원본 일정(periods)을 쓰고 끝만 달력 마지막 날로 자른다. 달력보다 앞서 시작한 날은 자르지 않는다.
    한계: 달력 끝에 걸린 기간은 그 뒤 날을 모르므로 실제보다 짧게 나올 수 있다.
    periods 에 없는 근거 id는 달력에 보인 첫날~마지막 날을 기간으로 쓴다.
    """
    seen_on: dict[str, list[dt.date]] = defaultdict(list)
    for cell in calendar:
        for reason in cell.reasons:
            if reason.tag != "WEATHER":
                seen_on[reason.ref_id].append(cell.date)
    if not seen_on:
        return {}
    last_day = max(cell.date for cell in calendar)
    period_by_id = {period.ref_id: period for period in periods}
    bounds = {}
    for ref_id, days in seen_on.items():
        period = period_by_id.get(ref_id)
        if period is None:
            bounds[ref_id] = (min(days), max(days))
        else:
            bounds[ref_id] = (period.start, min(period.end or last_day, last_day))
    return bounds


def menu_board_bases(
    calendar: list[CalendarCell],
    periods: list[TagPeriod],
    store: StoreSettings,
    k: int,
    cost_per_menu: float = COST_PER_MENU,
) -> dict[dt.date, str | None]:
    """영업일별 메뉴판 기준 태그(근거 id). None 이면 원래 순서다.

    1. 근거 id마다 교체 이득(_switch_benefit)이 교체 부담(cost_per_menu × k)보다 커야 바꿀 만하다. k 는 맨 위로 올릴 메뉴 수.
       기간은 tag_periods 를 따른다.
    2. 그날 붙은 태그 가운데 바꿀 만한 것 중에서 하루 효과(대표 |effect|)가 가장 큰 것이 기준 태그다.
       같으면 근거 id 순으로 앞선 것. 이득 합계로 고르지 않는 까닭: 기간이 긴 계절이 늘 이긴다.
    날씨는 기준 태그가 되지 않는다. 쉬는 날은 결과에 없다.
    """
    if not calendar:
        return {}
    effects: dict[str, list[float]] = defaultdict(list)
    for cell in calendar:
        for reason in cell.reasons:
            if reason.tag != "WEATHER":
                effects[reason.ref_id].append(reason.effect)
    bounds = tag_periods(calendar, periods)
    burden = cost_per_menu * k

    worthwhile: dict[str, float] = {}  # 바꿀 만한 근거 id → 하루 효과
    for ref_id, values in effects.items():
        if _switch_benefit(values, _open_days(*bounds[ref_id], store)) > burden + _EPSILON:
            worthwhile[ref_id] = _strength(values)

    bases = {}
    for day, day_tags in sorted(tags_by_date(calendar).items()):
        if is_closed_day(day, store):
            continue
        candidates = [ref_id for _, ref_id in day_tags if ref_id in worthwhile]
        bases[day] = min(candidates, key=lambda ref_id: (-worthwhile[ref_id], ref_id), default=None)
    return bases


def previous_open_day(day: dt.date, store: StoreSettings) -> dt.date:
    """plan_menu_orders 가 견주는 직전 영업일. 전날부터 거슬러 가되 일주일까지만 본다."""
    previous = day - dt.timedelta(days=1)
    while is_closed_day(previous, store) and (day - previous).days < 7:
        previous -= dt.timedelta(days=1)
    return previous


def unchanged_menu_orders(plan_items: list[PlanItem], bases: dict[dt.date, str | None], store: StoreSettings) -> set[str]:
    """plan_menu_orders 가 만든 메뉴판 카드 가운데 기준 태그가 직전 영업일과 같아 바뀌는 것이 없는 카드의 plan_id.

    예) 교체 이득이 부담을 넘지 못한 행사가 시작하거나 끝난 날의 카드. 그날이나 직전 영업일의 기준 태그를 모르면 넣지 않는다.
    """
    unchanged = set()
    for item in plan_items:
        if item.task_type != "MENU_ORDER":
            continue
        day = dt.date.fromisoformat(item.basis.ref_id)  # 메뉴판 카드의 근거는 날짜다
        previous = previous_open_day(day, store)
        if day in bases and previous in bases and bases[day] == bases[previous]:
            unchanged.add(item.plan_id)
    return unchanged
