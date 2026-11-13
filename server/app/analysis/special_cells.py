"""특별한 칸을 찾는다.

특별한 칸은 원본 조건(행사·경기·날씨 테이블)에 걸리는 칸이다. 과거 효과가 작아 달력 태그가 붙지 않는 칸도
포함한다(태그 판정은 store_calendar/past_effects 가 한다). 기준선은 이 칸들을 빼고 계산한다.
- EVENT: 매장에서 2km 안(2km 포함)이고, 행사 시간과 겹친 시간이 0보다 큰 칸
- GAME: 시작 시각이 속한 시간대와 그다음 시간대(저녁 시작이면 저녁만). 영업시간 밖에 시작하면 표시하지 않는다
- WEATHER: 비 5mm 이상, 최고 33도 이상, 최저 영하 12도 이하인 날의 모든 칸(날씨 데이터가 하루 단위다)
"""

import datetime as dt
from dataclasses import dataclass
from typing import Literal

from app.analysis.input_shapes import AnalysisInputs, WeatherDay
from app.analysis.pattern.daypart_time import daypart_at, dayparts_of, is_closed_day, overlap_minutes, window
from app.analysis.result_shapes import AnalysisDaypart
from app.core.seoul_time import to_seoul
from app.planner.data_shapes import EventKind, GameKind

EVENT_RADIUS_KM = 2.0
RAIN_MM = 5.0
HEAT_MAX_C = 33.0
COLD_MIN_C = -12.0

SpecialTag = Literal["EVENT", "GAME", "WEATHER"]
WeatherKind = Literal["RAIN", "HEAT", "COLD"]
SpecialKind = EventKind | GameKind | WeatherKind


@dataclass(frozen=True)
class SpecialCell:
    date: dt.date
    daypart: AnalysisDaypart
    tag: SpecialTag
    kind: SpecialKind  # 행사·경기 종류, 또는 날씨 종류. 과거 효과를 이 종류로 묶는다
    ref_id: str  # event_012, game_031, weather:2026-11-17:RAIN


def find_special_cells(inputs: AnalysisInputs, start: dt.date, end: dt.date) -> list[SpecialCell]:
    """start~end(양 끝 포함) 날짜에서 특별한 칸. 휴무일은 뺀다. 한 칸에 이유가 여러 개면 행도 여러 개다."""
    store = inputs.store
    ranges = dayparts_of(store)
    nearby_events = [e for e in inputs.events if e.distance_km <= EVENT_RADIUS_KM]
    weather = {w.date: w for w in inputs.weather}
    result = []
    day = start
    while day <= end:
        if not is_closed_day(day, store):
            for r in ranges:
                cell_start, cell_end = window(day, r, store)
                for e in nearby_events:
                    if overlap_minutes(e.start_at, e.end_at, cell_start, cell_end) > 0:
                        result.append(SpecialCell(day, r.daypart, "EVENT", e.kind, e.event_id))
            for g in inputs.games:
                if to_seoul(g.start_at).date() != day:
                    continue
                start_daypart = daypart_at(g.start_at, ranges)
                if start_daypart is None:
                    continue
                i = [r.daypart for r in ranges].index(start_daypart)
                for r in ranges[i : i + 2]:
                    result.append(SpecialCell(day, r.daypart, "GAME", g.kind, g.game_id))
            for kind in _weather_kinds(weather.get(day)):
                for r in ranges:
                    result.append(SpecialCell(day, r.daypart, "WEATHER", kind, f"weather:{day.isoformat()}:{kind}"))
        day += dt.timedelta(days=1)
    return result


def cell_keys(cells: list[SpecialCell]) -> set[tuple[dt.date, AnalysisDaypart]]:
    """기준선에서 뺄 칸 집합. 이유가 여러 개인 칸도 한 번만 들어간다."""
    return {(c.date, c.daypart) for c in cells}


def _weather_kinds(w: WeatherDay | None) -> list[WeatherKind]:
    """그날 걸린 날씨 조건. 여러 개일 수 있다."""
    if w is None:
        return []
    kinds: list[WeatherKind] = []
    if w.rain_mm is not None and w.rain_mm >= RAIN_MM:
        kinds.append("RAIN")
    if w.temp_max is not None and w.temp_max >= HEAT_MAX_C:
        kinds.append("HEAT")
    if w.temp_min is not None and w.temp_min <= COLD_MIN_C:
        kinds.append("COLD")
    return kinds
