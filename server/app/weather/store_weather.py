"""가게 지역 날씨를 받아 그 가게 파일(db/data/s101.db ...)에 저장한다.

사장님이 가게를 등록하면(app/modules/stores/router.py) 가게 좌표(네이버 지도에서 읽어 store 표에 둔 lat, lng)로
기상청 날씨를 받는다. 사장님이 위도·경도를 적지 않는다.

    store_weather_daily  날짜마다 한 줄. 지난날은 관측, 오늘부터는 예보. 분석(태성)이 읽는다 (read_store_db.read_weather)
    store_weather_fetch  마지막으로 받은 전체 결과(시간별 예보, 위치·관측소 정보). 한 줄
    store_weather_forecast_history  받을 때마다 받은 예보의 하루 요약. (대상 날짜, 발표 시각) 한 줄, 지우지 않는다.
                         위 두 표는 지난 예보를 남기지 않아서, 그때 있던 예보로 얼마나 맞혔는지 나중에 잴 수 있게 더했다
                         (read_store_db.forecast_as_of)

목업 가게(s001~s003)는 공통 목업 날씨를 쓴다. 목업 가게로 이은 실제 가게(s004 피플스클럽, s005 초옹장)는 사장님이 등록하면
등록한 가게처럼 받는다. 다만 git 에 올라간 목업 파일을 고치지 않게 db/app_data/weather/<가게>.db 에 저장하고,
분석은 받은 날만 기상청 날씨로 바꾼다 (read_store_db.read_weather).
"""

import datetime as dt

from sqlalchemy import delete, insert, select

from app.core.config import settings
from app.data_pipeline import read_store_db, registered_stores
from app.weather.client import KmaClient, KmaError
from app.weather.schemas import WeatherResult
from app.weather.service import get_weather
from db import models

PAST_DAYS = 30
DAILY = models.StoreWeatherDaily.__table__
FETCH = models.StoreWeatherFetch.__table__
HISTORY = models.StoreWeatherForecastHistory.__table__


def can_fetch(store_id: str) -> bool:
    """인증키가 있고, 사장님이 등록한 가게(s101 부터, 또는 사장님이 등록한 목업 가게로 이은 s004·s005)인지."""
    if registered_stores.is_mock_store(store_id):
        registered = registered_stores.place_info(store_id) is not None
    else:
        registered = store_id[1:].isdigit() and int(store_id[1:]) >= registered_stores.FIRST_NUMBER
    return bool(settings.kma_api_key) and registered


def update_store_weather(store_id: str, client: KmaClient | None = None, now: dt.datetime | None = None) -> dict:
    """가게 좌표로 날씨를 받아 저장한다. 아무것도 받지 못하면 첫 오류를 낸다. 저장한 요약을 돌려준다.

    이미 관측을 저장해 둔 날은 다시 부르지 않는다 (3시간마다 새로 받을 때 일자료 30번 호출을 줄인다).
    """
    store = read_store_db.read_store(store_id)
    observed = {r["date"] for r in read_store_db.read_store_weather(store_id) if r["kind"] == "observed"}
    result = get_weather(store["lat"], store["lng"], past_days=PAST_DAYS, client=client, now=now, skip_observation_dates=observed)
    got_any = any(o.temperature_avg is not None or o.precipitation_mm is not None for o in result.observations)
    if not (got_any or result.forecasts.daily):
        first = result.metadata.errors[0] if result.metadata.errors else None
        raise KmaError(f"{first.section}: {first.message}" if first else "기상청에서 받은 날씨가 없어요")
    return save(store_id, result)


def _daily_rows(result: WeatherResult, fetched_at: dt.datetime) -> list[dict]:
    rows = []
    for o in result.observations:
        if all(v is None for v in (o.temperature_avg, o.temperature_max, o.temperature_min, o.precipitation_mm, o.cloud_cover)):
            continue  # 받지 못한 날은 저장하지 않는다 (예전에 받은 값을 지우지 않게)
        rows.append({
            "date": o.date, "kind": "observed", "source": o.source,
            "temp_avg": o.temperature_avg, "temp_max": o.temperature_max, "temp_min": o.temperature_min,
            "sky": o.sky, "precip_type": o.precipitation_type, "precip_mm": o.precipitation_mm,
            "pop_max": None, "issued_at": None, "fetched_at": fetched_at,
        })
    for f in result.forecasts.daily:
        rows.append({
            "date": f.date, "kind": "forecast", "source": f.source,
            "temp_avg": None, "temp_max": f.temperature_max, "temp_min": f.temperature_min,
            "sky": f.sky, "precip_type": f.precipitation_type, "precip_mm": f.precipitation_mm_min,
            "pop_max": round(f.precipitation_probability_max) if f.precipitation_probability_max is not None else None,
            "issued_at": f.issued_at, "fetched_at": fetched_at,
        })
    return rows


def _history_rows(result: WeatherResult, fetched_at: dt.datetime) -> list[dict]:
    """예보 이력 표 줄: 받은 예보의 하루 요약 모두. 값은 _daily_rows 의 예보 줄과 같고 hours 를 더한다."""
    return [
        {
            "date": f.date, "issued_at": f.issued_at, "source": f.source,
            "temp_max": f.temperature_max, "temp_min": f.temperature_min,
            "sky": f.sky, "precip_type": f.precipitation_type, "precip_mm": f.precipitation_mm_min,
            "pop_max": round(f.precipitation_probability_max) if f.precipitation_probability_max is not None else None,
            "hours": f.hours, "fetched_at": fetched_at,
        }
        for f in result.forecasts.daily
    ]


def save(store_id: str, result: WeatherResult) -> dict:
    """관측은 같은 날 예보를 대신한다. 예보는 관측이 있는 날과 지난날에는 넣지 않고, 지난날 예보는 지운다.

    받은 예보의 하루 요약은 예보 이력 표에도 쌓는다. 같은 (날짜, 발표 시각)는 덮어쓰고 지우지 않는다.
    """
    fetched_at = result.metadata.requested_at
    today = fetched_at.date()
    rows = _daily_rows(result, fetched_at)
    with read_store_db.weather_engine(store_id).begin() as conn:
        DAILY.create(conn, checkfirst=True)
        FETCH.create(conn, checkfirst=True)
        # 예보 이력: store_weather_daily 아래 동작(관측이 예보 대신, 지난날 예보 삭제)은 그대로 두고, 지난 예보는 이 표에만 남긴다
        HISTORY.create(conn, checkfirst=True)
        history = _history_rows(result, fetched_at)
        for h in history:
            conn.execute(delete(HISTORY).where(HISTORY.c.date == h["date"], HISTORY.c.issued_at == h["issued_at"]))
        if history:
            conn.execute(insert(HISTORY), history)
        conn.execute(delete(DAILY).where(DAILY.c.kind == "forecast", DAILY.c.date < today))
        observed = {r.date for r in conn.execute(select(DAILY.c.date).where(DAILY.c.kind == "observed"))}
        observed |= {r["date"] for r in rows if r["kind"] == "observed"}
        keep = [r for r in rows if r["kind"] == "observed" or (r["date"] >= today and r["date"] not in observed)]
        if keep:
            conn.execute(delete(DAILY).where(DAILY.c.date.in_([r["date"] for r in keep])))
            conn.execute(insert(DAILY), keep)
        conn.execute(delete(FETCH))
        conn.execute(insert(FETCH), [{"fetch_id": 1, "fetched_at": fetched_at, "payload": result.model_dump(mode="json")}])
    return {
        "store_id": store_id,
        "fetched_at": fetched_at.isoformat(),
        "observed_days": sum(r["kind"] == "observed" for r in keep),
        "forecast_days": sum(r["kind"] == "forecast" for r in keep),
        "location": result.location.model_dump(mode="json"),
        "errors": [e.model_dump() for e in result.metadata.errors],
    }


def saved_weather(store_id: str) -> dict:
    """저장해 둔 날씨 (가게 날씨 조회 API). 받은 적이 없으면 days 가 비어 있다."""
    days = read_store_db.read_store_weather(store_id)
    fetch = read_store_db.read_store_weather_fetch(store_id)
    payload = fetch["payload"] if fetch else {}
    return {
        "store_id": store_id,
        "fetched_at": fetch["fetched_at"].isoformat() if fetch else None,
        "location": payload.get("location"),
        "metadata": payload.get("metadata"),
        "days": [
            {**{k: (float(v) if k in ("temp_avg", "temp_max", "temp_min", "precip_mm") and v is not None else v) for k, v in d.items()},
             "date": d["date"].isoformat(),
             "issued_at": d["issued_at"].isoformat() if d["issued_at"] else None,
             "fetched_at": d["fetched_at"].isoformat()}
            for d in days
        ],
    }
