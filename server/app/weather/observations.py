"""지난 날씨: ASOS 일자료 (kma_sfcdd.php). 날짜마다 한 번씩 부른다.

- 가게에서 가장 가까운 관측소부터 시도해, 어제(가장 최근) 기온이 있는 첫 관측소를 쓴다 (최대 3곳).
- 관측소는 가게와 떨어져 있다. 결과의 location.station.distance_km 와 metadata.notes 에 적는다.
- 결측: 기온 칸(TA_*)은 -99 이하, 나머지 칸(강수, 적설, 전운량 등 0 이상인 값)은 -9 이하를 null 로 본다.
- 실제 응답(2026-11 춘천 30일)을 보면 비 온 날은 일강수량이 숫자(0.2, 29.7 …), 아주 약한 비는 0.0,
  비가 오지 않은 맑은 날은 모두 -9 다. 그래서 일강수량 숫자는 null 로 두되(0 으로 만들지 않음),
  그날 기온 관측이 있으면 강수형태는 '없음'으로 본다. 기온도 없는 날(관측 자체가 빠진 날)은 강수형태도 null.
- 하늘상태: 일 평균 전운량(CA_TOT, 0~10)을 단기예보 하늘상태 기준으로 나눈다. 0~5 맑음, 6~8 구름많음, 9~10 흐림.
- 강수형태: 신적설(SD_NEW)이 있으면 눈, 일강수량이 0 보다 크면 비, 0 이거나 -9(위 설명)면 없음.
"""

import datetime as dt
import math

from app.weather.client import KmaClient, KmaNoDataError
from app.weather.parsing import typ01_rows
from app.weather.schemas import ObservedDay, PrecipType, Sky, Station

DAILY_PATH = "/api/typ01/url/kma_sfcdd.php"
CANDIDATES = 3

# 결과 칸 ← ASOS 일자료 칸
FIELDS = {
    "temperature_avg": "TA_AVG",
    "temperature_min": "TA_MIN",
    "temperature_max": "TA_MAX",
    "precipitation_mm": "RN_DAY",
    "new_snow_cm": "SD_NEW",
    "cloud_cover": "CA_TOT",
}


def observed_value(column: str, raw: str | None) -> float | None:
    if raw is None:
        return None
    try:
        value = float(raw)
    except ValueError:
        return None
    if column.startswith("TA_"):
        return None if value <= -99 else value
    return None if value <= -9 else value


def sky_from_cloud(cloud_cover: float | None) -> Sky | None:
    if cloud_cover is None:
        return None
    tenths = math.floor(cloud_cover + 0.5)
    return "맑음" if tenths <= 5 else "구름많음" if tenths <= 8 else "흐림"


def precip_type_observed(precip_mm: float | None, new_snow_cm: float | None, observed: bool) -> PrecipType | None:
    """observed: 그날 기온 관측이 있다 (관측 자체는 됐다)."""
    if new_snow_cm:
        return "눈"
    if precip_mm is not None and precip_mm > 0:
        return "비"
    if precip_mm is not None or observed:
        return "없음"
    return None


def parse_daily(text: str, station_id: int, day: dt.date) -> ObservedDay | None:
    """그 관측소, 그날 한 줄. 없으면 None."""
    for row in typ01_rows(text, ["TM", "STN", "TA_AVG"]):
        if row["STN"] == str(station_id) and row["TM"][:8] == day.strftime("%Y%m%d"):
            values = {name: observed_value(col, row.get(col)) for name, col in FIELDS.items()}
            return ObservedDay(
                date=day,
                station_id=station_id,
                **values,
                sky=sky_from_cloud(values["cloud_cover"]),
                precipitation_type=precip_type_observed(values["precipitation_mm"], values["new_snow_cm"], values["temperature_avg"] is not None),
            )
    return None


def fetch_day(client: KmaClient, station_id: int, day: dt.date) -> ObservedDay | None:
    try:
        text = client.get_text(DAILY_PATH, {"tm": day.strftime("%Y%m%d"), "stn": station_id, "disp": "1", "help": "1"})
    except KmaNoDataError:
        return None
    return parse_daily(text, station_id, day)


def fetch_observations(client: KmaClient, candidates: list[Station], dates: list[dt.date]) -> tuple[Station, list[ObservedDay]]:
    """dates(오래된 날부터)의 관측. 자료가 없는 날도 값이 모두 null 인 줄로 남긴다 (만들어 채우지 않는다)."""
    by_date: dict[dt.date, ObservedDay | None] = {}
    latest = dates[-1]
    station = None
    for candidate in candidates[:CANDIDATES]:
        day = fetch_day(client, candidate.station_id, latest)
        if day and day.temperature_avg is not None:
            station, by_date[latest] = candidate, day
            break
    if station is None:  # 어제 자료가 아직 없을 수 있다. 가장 가까운 관측소로 받는다
        station = candidates[0]
    for day in dates:
        if day not in by_date:
            by_date[day] = fetch_day(client, station.station_id, day)
    return station, [by_date[d] or ObservedDay(date=d, station_id=station.station_id) for d in dates]
