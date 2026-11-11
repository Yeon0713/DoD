"""우리 매장 달력(calendar_day)을 만든다.

now 의 날짜부터 35일 × 시간대 칸마다 기준선, 예상 매출, 비율, 신호, 이유를 정한다. 휴무일은 칸이 없다.
- 이유: 그 칸의 특별한 칸 중 과거 효과가 ±10% 이상인 것(tagged_effect). 같은 묶음은 ref_id 가 앞선 하나만 남긴다
- 계절이 있으면 ±10% 판정 없이 항상 SEASON 이유(+5%)를 붙인다
- 이유의 효과는 소수 둘째 자리로 저장하고, 예상 매출 = 기준선 × (1 + Σ 효과)를 내림한다. 0원 아래로는 내려가지 않는다
- 비율은 예상 ÷ 기준선을 소수 둘째 자리로 반올림하고, 그 비율로 신호를 정한다(1.15 이상 HIGH, 0.85 이하 LOW)
- 기준선이 없거나 0원인 칸은 효과 판정을 건너뛴다: 예상·비율은 None, 신호 NORMAL, 이유 없음(기준선 0은 그대로 둔다)
"""

import datetime as dt
from dataclasses import dataclass

from app.analysis.input_shapes import AnalysisInputs, require_aware
from app.analysis.pattern.baseline import Cell, build_baselines
from app.analysis.pattern.daypart_time import dayparts_of, is_closed_day, weekday_of
from app.analysis.pattern.sales_daily import build_sales_daily
from app.analysis.result_shapes import AnalysisDaypart, CalendarDayRow
from app.analysis.special_cells import SpecialCell, WeatherKind, cell_keys, find_special_cells
from app.analysis.store_calendar.past_effects import EffectGroup, EffectKey, PastEffect, build_past_effects, tagged_effect
from app.analysis.store_calendar.reason_text import NamedReason, reason_text
from app.analysis.store_calendar.season import SEASON_EFFECT, Season, season_ref_id, seasons_between
from app.core.seoul_time import to_seoul
from app.planner.data_shapes import CalendarReason, Signal

CALENDAR_DAYS = 35
HIGH_RATIO = 1.15
LOW_RATIO = 0.85
WEATHER_NAMES: dict[WeatherKind, str] = {"RAIN": "비", "HEAT": "폭염", "COLD": "한파"}
SEASON_NAMES: dict[Season, str] = {"WINTER": "겨울", "SUMMER": "여름"}


@dataclass(frozen=True)
class _Reason:
    """달력 이유와, 이유 문장에 쓸 이름."""

    reason: CalendarReason
    name: str


def build_calendar_days(inputs: AnalysisInputs, now: dt.datetime) -> list[CalendarDayRow]:
    """now 의 날짜부터 35일 달력 칸. computed_at 은 now 다."""
    require_aware(now)
    store = inputs.store
    dayparts = [r.daypart for r in dayparts_of(store)]
    today = to_seoul(now).date()
    last_day = today + dt.timedelta(days=CALENDAR_DAYS - 1)
    rows = build_sales_daily(inputs, now).rows

    past_special = find_special_cells(inputs, rows[0].date, today) if rows else []
    baselines = build_baselines(rows, cell_keys(past_special), today, dayparts)
    effects = build_past_effects(inputs, rows, now)
    special_by_cell: dict[Cell, list[SpecialCell]] = {}
    for cell in find_special_cells(inputs, today, last_day):
        special_by_cell.setdefault((cell.date, cell.daypart), []).append(cell)
    titles_by_ref_id = {**{e.event_id: e.title for e in inputs.events}, **{g.game_id: g.title for g in inputs.games}}
    seasons = seasons_between(inputs.weather, today, last_day)

    calendar = []
    for offset in range(CALENDAR_DAYS):
        day = today + dt.timedelta(days=offset)
        if is_closed_day(day, store):
            continue
        for daypart in dayparts:
            baseline = baselines[(weekday_of(day), daypart)]
            if not baseline:  # 없거나 0원이면 비율을 구할 수 없다
                calendar.append(_calendar_row_without_ratio(day, daypart, baseline, now))
                continue
            reasons = _reasons_for(special_by_cell.get((day, daypart), []), daypart, effects, titles_by_ref_id, seasons[day])
            calendar.append(_calendar_row(day, daypart, baseline, reasons, now))
    return calendar


def _reasons_for(
    cells: list[SpecialCell],
    daypart: AnalysisDaypart,
    effects: dict[EffectKey, PastEffect],
    titles_by_ref_id: dict[str, str],
    season: Season | None,
) -> list[_Reason]:
    """한 칸의 이유. 태그가 붙는 특별한 칸(같은 묶음은 ref_id 가 앞선 하나)과 계절."""
    reasons = []
    seen_groups: set[EffectGroup] = set()
    for cell in sorted(cells, key=lambda c: c.ref_id):
        group: EffectGroup = (cell.tag, cell.kind)
        if group in seen_groups:
            continue
        seen_groups.add(group)
        effect = tagged_effect(effects, group, daypart)
        if effect is None:
            continue
        name = WEATHER_NAMES[cell.kind] if cell.tag == "WEATHER" else titles_by_ref_id[cell.ref_id]
        reasons.append(_Reason(CalendarReason(tag=cell.tag, ref_id=cell.ref_id, effect=round(effect, 2)), name))
    if season is not None:
        reasons.append(_Reason(CalendarReason(tag="SEASON", ref_id=season_ref_id(season), effect=SEASON_EFFECT), SEASON_NAMES[season]))
    return reasons


def _calendar_row(
    day: dt.date,
    daypart: AnalysisDaypart,
    baseline: int,
    reasons: list[_Reason],
    now: dt.datetime,
) -> CalendarDayRow:
    total_percent = round(sum(r.reason.effect for r in reasons) * 100)  # 효과는 소수 둘째 자리라 정수 퍼센트다
    expected = max(0, baseline * (100 + total_percent) // 100)  # 정수로 내림한다(실수 곱셈의 574,999.999… 오차를 피한다)
    ratio = round(expected / baseline, 2)
    return CalendarDayRow(
        date=day,
        daypart=daypart,
        signal=_signal(ratio),
        baseline_sales=baseline,
        expected_sales=expected,
        ratio=ratio,
        reasons=[r.reason for r in reasons],
        reason_text=reason_text([NamedReason(r.name, r.reason.effect) for r in reasons], ratio),
        computed_at=now,
    )


def _calendar_row_without_ratio(day: dt.date, daypart: AnalysisDaypart, baseline: int | None, now: dt.datetime) -> CalendarDayRow:
    return CalendarDayRow(
        date=day,
        daypart=daypart,
        signal="NORMAL",
        baseline_sales=baseline,
        expected_sales=None,
        ratio=None,
        reasons=[],
        reason_text=reason_text([], None),
        computed_at=now,
    )


def _signal(ratio: float) -> Signal:
    if ratio >= HIGH_RATIO:
        return "HIGH"
    if ratio <= LOW_RATIO:
        return "LOW"
    return "NORMAL"
