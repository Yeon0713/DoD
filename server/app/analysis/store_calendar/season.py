"""계절을 정한다.

계절은 최고기온이 며칠 이어서 한쪽으로 넘어가 있는 기간(여름·겨울)이다. 그 사이에는 계절이 없다.
- 겨울: 최고 10도 미만이 3일 연속이면 그 첫날부터, 10도 이상이 3일 연속이면 그 첫날부터 끝
- 여름: 최고 25도 초과가 3일 연속이면 그 첫날부터, 25도 이하가 3일 연속이면 그 첫날부터 끝
- 경계값은 시작과 끝이 맞물리게 정했다. 여름에서 바로 겨울로 넘어갈 수도 있다
날씨 기록 전체(지난 관측 + 앞날 예보)를 처음부터 훑어 정한다. 기록이 빠진 날은 기온을 모르므로 3일 연속을 끊고,
기록이 끝난 뒤의 날은 마지막 계절을 이어 간다.
"""

import datetime as dt
from typing import Literal

from app.analysis.input_shapes import WeatherDay

Season = Literal["WINTER", "SUMMER"]

SEASON_EFFECT = 0.05  # 계절 효과 +5% 고정 [가정]. ±10% 태그 판정의 대상이 아니다(계절이 있으면 항상 태그)
RUN_DAYS = 3  # 조건이 이만큼 이어져야 계절이 바뀐다
WINTER_BELOW_C = 10.0
SUMMER_ABOVE_C = 25.0


def seasons_between(weather: list[WeatherDay], start: dt.date, end: dt.date) -> dict[dt.date, Season | None]:
    """start~end(양 끝 포함) 날짜마다 계절."""
    changes = _season_changes(weather)
    result = {}
    day = start
    while day <= end:
        result[day] = _season_on(day, changes)
        day += dt.timedelta(days=1)
    return result


def season_ref_id(season: Season) -> str:
    """달력 이유의 ref_id. 예) season_winter"""
    return f"season_{season.lower()}"


def _season_changes(weather: list[WeatherDay]) -> list[tuple[dt.date, Season | None]]:
    """(바뀐 날, 새 계절) 목록. 바뀐 날은 조건을 채운 3일 중 첫날이다.

    같은 날짜가 여러 번 오면 입력에서 나중에 온 값만 쓴다.
    """
    latest = {w.date: w.temp_max for w in weather}  # 같은 날짜는 나중 값이 남는다
    latest = {d: t for d, t in latest.items() if t is not None}  # 최고기온을 모르는 날은 빠진 날로 본다
    dates = sorted(latest)
    changes: list[tuple[dt.date, Season | None]] = []
    season: Season | None = None
    for i in range(RUN_DAYS - 1, len(dates)):
        run = dates[i - RUN_DAYS + 1 : i + 1]
        if (run[-1] - run[0]).days != RUN_DAYS - 1:  # 사이에 빠진 날이 있다
            continue
        next_season = _next_season(season, [latest[d] for d in run])
        if next_season != season:
            season = next_season
            changes.append((run[0], season))
    return changes


def _next_season(season: Season | None, temps: list[float]) -> Season | None:
    """지금 계절과 이어진 3일의 최고기온으로 다음 계절."""
    if season != "WINTER" and all(t < WINTER_BELOW_C for t in temps):
        return "WINTER"
    if season != "SUMMER" and all(t > SUMMER_ABOVE_C for t in temps):
        return "SUMMER"
    if season == "WINTER" and all(t >= WINTER_BELOW_C for t in temps):
        return None
    if season == "SUMMER" and all(t <= SUMMER_ABOVE_C for t in temps):
        return None
    return season


def _season_on(day: dt.date, changes: list[tuple[dt.date, Season | None]]) -> Season | None:
    """day 이전(그날 포함)에 마지막으로 바뀐 계절."""
    current = None
    for changed_on, season in changes:
        if changed_on > day:
            break
        current = season
    return current
