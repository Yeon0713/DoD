"""날씨 결과 모양. get_weather 가 WeatherResult 를 돌려주고, .model_dump(mode="json") 이 weather.json 모양이다.

- 지난날은 ASOS 관측(observations), 오늘부터는 단기예보(forecasts). 섞지 않고 행마다 type 과 source 가 붙는다.
- 예보는 발표 시각(issued_at)과 대상 시각(datetime/date)을 따로 둔다.
- 값이 없으면 null. 0 으로 채우지 않는다.
- 날씨 구분은 하늘상태(sky: 맑음/구름많음/흐림)와 강수형태(precipitation_type: 없음/비/비/눈/눈/소나기) 두 가지다.
"""

import datetime as dt
from typing import Literal

from pydantic import AwareDatetime, BaseModel, Field

Sky = Literal["맑음", "구름많음", "흐림"]
PrecipType = Literal["없음", "비", "비/눈", "눈", "소나기"]


class Station(BaseModel):
    """ASOS 관측소 (기상청 지점정보)."""

    station_id: int
    name: str | None = None
    latitude: float
    longitude: float
    distance_km: float | None = None  # 가게에서 관측소까지 거리


class Location(BaseModel):
    latitude: float
    longitude: float
    nx: int  # 단기예보 격자 (5km 칸)
    ny: int
    station: Station | None = None  # 지난 관측에 쓴 ASOS 관측소. 가게 위치와 다르다


class ObservedDay(BaseModel):
    date: dt.date
    type: Literal["observed"] = "observed"
    source: Literal["asos_daily"] = "asos_daily"
    station_id: int
    temperature_avg: float | None = None
    temperature_min: float | None = None
    temperature_max: float | None = None
    precipitation_mm: float | None = None  # 일강수량. 관측소가 -9(비 안 온 날 또는 결측)를 주면 null
    new_snow_cm: float | None = None  # 그날 최심 신적설
    cloud_cover: float | None = None  # 일 평균 전운량 (0~10)
    sky: Sky | None = None  # 전운량으로 정함
    precipitation_type: PrecipType | None = None  # 강수량·신적설로 정함. 비 안 온 날(-9)은 없음


class HourlyForecast(BaseModel):
    datetime: AwareDatetime  # 예보 대상 시각
    type: Literal["forecast"] = "forecast"
    source: Literal["short_term"] = "short_term"
    issued_at: AwareDatetime  # 발표 시각
    temperature: float | None = None  # TMP (℃)
    sky: Sky | None = None  # SKY
    precipitation_type: PrecipType | None = None  # PTY
    precipitation_probability: float | None = None  # POP (%)
    precipitation_text: str | None = None  # PCP 원문. 예) "강수없음", "1mm 미만", "30.0~50.0mm"
    precipitation_mm_min: float | None = None  # PCP 범주의 아래 끝
    snow_text: str | None = None  # SNO 원문


class DailyForecast(BaseModel):
    date: dt.date
    type: Literal["forecast"] = "forecast"
    source: Literal["short_term"] = "short_term"
    issued_at: AwareDatetime
    temperature_min: float | None = None  # TMN
    temperature_max: float | None = None  # TMX
    sky: Sky | None = None  # 그날 시간별 하늘상태 중 가장 많은 것 (같으면 더 흐린 쪽)
    precipitation_type: PrecipType | None = None  # 그날 시간별 강수형태를 합친 것
    precipitation_mm_min: float | None = None  # 시간별 PCP 아래 끝의 합 (적어도 이만큼)
    precipitation_probability_max: float | None = None
    hours: int  # 그날 시간별 예보 개수 (24 보다 작으면 일부 시간만)


class Forecasts(BaseModel):
    hourly: list[HourlyForecast] = []
    daily: list[DailyForecast] = []


class SectionError(BaseModel):
    section: Literal["stations", "observations", "short_forecast"]
    code: str
    message: str


class Metadata(BaseModel):
    requested_at: AwareDatetime
    short_forecast_issued_at: AwareDatetime | None = None
    forecast_end_at: AwareDatetime | None = None  # 지금 받은 단기예보의 마지막 시각
    notes: list[str] = []
    errors: list[SectionError] = []  # 실패한 부분. 다른 부분은 그대로 돌려준다


class WeatherResult(BaseModel):
    location: Location
    timezone: Literal["Asia/Seoul"] = "Asia/Seoul"
    observations: list[ObservedDay] = []
    forecasts: Forecasts = Field(default_factory=Forecasts)
    metadata: Metadata
