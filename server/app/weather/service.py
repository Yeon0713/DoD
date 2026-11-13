"""위도·경도 하나의 날씨: 지난 관측(ASOS 일자료) + 오늘부터 단기예보.

    from app.weather.service import get_weather
    result = get_weather(latitude=37.8813, longitude=127.7298, past_days=30)
    result.model_dump(mode="json")   # weather.json 모양 (app/weather/schemas.py)

가게 날씨는 가게 좌표로 이 함수를 부른다 (app/weather/store_weather.py). 사장님이 위도·경도를 적지 않는다.
한 부분이 실패해도(예: 일자료 활용신청이 아직 승인 안 됨) 나머지는 돌려주고, 실패는 metadata.errors 에 적는다.
"""

import datetime as dt

from app.core.seoul_time import SEOUL
from app.weather.client import KmaClient, KmaError
from app.weather.coordinates import to_grid
from app.weather.observations import fetch_observations
from app.weather.schemas import Forecasts, Location, Metadata, SectionError, WeatherResult
from app.weather.short_forecast import fetch_short_forecast
from app.weather.stations import fetch_stations, nearest_stations


def get_weather(
    latitude: float,
    longitude: float,
    past_days: int = 30,
    include_forecast: bool = True,
    *,
    client: KmaClient | None = None,
    now: dt.datetime | None = None,
    skip_observation_dates: set[dt.date] | None = None,
) -> WeatherResult:
    """skip_observation_dates: 이미 관측을 저장해 둔 날. 다시 부르지 않는다 (어제는 관측소 고르기에 쓰므로 늘 부른다)."""
    client = client or KmaClient.from_settings()
    # 기상청 자료는 실제 시각 기준이다. 개발용 시계 앞당김(now_seoul)은 쓰지 않는다
    now = (now or dt.datetime.now(SEOUL)).astimezone(SEOUL)
    nx, ny = to_grid(latitude, longitude)
    location = Location(latitude=latitude, longitude=longitude, nx=nx, ny=ny)
    meta = Metadata(requested_at=now)

    def failed(section, error: KmaError) -> None:
        meta.errors.append(SectionError(section=section, code=error.code, message=str(error)))

    observations = []
    if past_days > 0:
        dates = [now.date() - dt.timedelta(days=n) for n in range(past_days, 0, -1)]
        skip = (skip_observation_dates or set()) - {dates[-1]}
        dates = [d for d in dates if d not in skip]
        try:
            stations = nearest_stations(fetch_stations(client, now), latitude, longitude)
        except KmaError as error:
            failed("stations", error)
        else:
            try:
                location.station, observations = fetch_observations(client, stations, dates)
                meta.notes.append(
                    f"지난 관측은 가게가 아니라 {location.station.distance_km}km 떨어진 ASOS 관측소 "
                    f"{location.station.station_id}({location.station.name or '이름 없음'}) 값이에요. "
                    "예보는 가게가 있는 5km 격자 값이에요."
                )
            except KmaError as error:
                failed("observations", error)

    forecasts = Forecasts()
    if include_forecast:
        try:
            meta.short_forecast_issued_at, forecasts.hourly, forecasts.daily = fetch_short_forecast(client, nx, ny, now)
            if forecasts.hourly:
                meta.forecast_end_at = forecasts.hourly[-1].datetime
        except KmaError as error:
            failed("short_forecast", error)

    return WeatherResult(location=location, observations=observations, forecasts=forecasts, metadata=meta)
