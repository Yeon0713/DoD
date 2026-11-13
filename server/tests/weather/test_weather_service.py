"""전체 흐름: 가게 좌표 → 지난 관측 + 단기예보 → 가게 DB 저장 → 분석 입력. 기상청은 가짜 응답."""

import datetime as dt

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import insert

from app.core.config import settings
from app.core.seoul_time import SEOUL
from app.data_pipeline import read_store_db, registered_stores
from app.data_pipeline.db_rows_to_analysis_inputs import build_analysis_inputs
from app.main import create_app
from app.modules.stores import router as stores_router
from app.weather import store_weather
from app.weather.client import KmaAuthError
from app.weather.service import get_weather
from db import models, session
from kma_samples import FakeKma

NOW = dt.datetime(2026, 11, 13, 14, 5, tzinfo=SEOUL)
CHUNCHEON = (37.8813, 127.7298)


def test_get_weather_joins_past_observations_and_short_forecast():
    fake = FakeKma(missing_day=dt.date(2026, 11, 1))
    result = get_weather(*CHUNCHEON, past_days=30, client=fake, now=NOW)

    loc = result.location
    assert (loc.nx, loc.ny, loc.station.station_id) == (73, 134, 101) and loc.station.distance_km < 3

    obs = result.observations
    assert len(obs) == 30 and obs[0].date == dt.date(2026, 10, 14) and obs[-1].date == dt.date(2026, 11, 12)  # 30일 전 ~ 어제
    assert all(o.type == "observed" and o.station_id == 101 for o in obs)
    missing = next(o for o in obs if o.date == dt.date(2026, 11, 1))
    assert missing.temperature_avg is None and missing.precipitation_mm is None and missing.precipitation_type is None  # 결측은 null
    rainy = next(o for o in obs if o.date == dt.date(2026, 11, 7))
    assert (rainy.sky, rainy.precipitation_type, rainy.precipitation_mm) == ("흐림", "비", 12.5)

    meta = result.metadata
    assert meta.short_forecast_issued_at == dt.datetime(2026, 11, 13, 8, 0, tzinfo=SEOUL)  # 11시 자료가 아직 없어 직전 발표
    assert meta.forecast_end_at == result.forecasts.hourly[-1].datetime == dt.datetime(2026, 11, 16, 23, 0, tzinfo=SEOUL)
    assert meta.errors == [] and any("관측소" in note for note in meta.notes)
    assert [d.date for d in result.forecasts.daily] == [dt.date(2026, 11, d) for d in (13, 14, 15, 16)]

    # 쓰는 API 는 지점정보, ASOS 일자료, 단기예보 셋뿐이다. 관측소 목록은 한 번, 일자료는 날짜마다 한 번
    paths = [p for p, _ in fake.calls]
    assert {p.rsplit("/", 1)[-1] for p in paths} == {"stn_inf.php", "kma_sfcdd.php", "getVilageFcst"}
    assert sum(p.endswith("stn_inf.php") for p in paths) == 1
    assert sum(p.endswith("kma_sfcdd.php") for p in paths) == 30


def test_one_failing_api_does_not_hide_the_others():
    fake = FakeKma(errors={"kma_sfcdd": KmaAuthError("활용신청 안 됨")})
    result = get_weather(*CHUNCHEON, client=fake, now=NOW)
    assert [(e.section, e.code) for e in result.metadata.errors] == [("observations", "KMA_AUTH")]
    assert result.observations == [] and result.forecasts.daily


def test_station_list_failure_skips_observations_but_keeps_forecast():
    fake = FakeKma(errors={"stn_inf.php": KmaAuthError("x")})
    result = get_weather(*CHUNCHEON, client=fake, now=NOW)
    assert [e.section for e in result.metadata.errors] == ["stations"]
    assert result.observations == [] and result.location.station is None
    assert result.forecasts.hourly


# ── 가게 DB ──


@pytest.fixture
def store_s150(tmp_path, monkeypatch):
    """임시 폴더에 등록한 가게 파일 s150 (춘천 좌표)을 만든다. 실제 db/data 는 건드리지 않는다."""
    monkeypatch.setattr(session, "DATA_DIR", tmp_path)
    monkeypatch.setattr(registered_stores, "DATA_DIR", tmp_path)
    registered_stores._create_store_file("s150")
    with session.store_engine("s150").begin() as conn:
        conn.execute(insert(models.Store), [{
            "store_id": "s150", "name": "시험 가게", "category": "돈가스", "address": "강원 춘천시", "lat": CHUNCHEON[0], "lng": CHUNCHEON[1],
            "open_time": dt.time(11), "close_time": dt.time(21), "closed_weekdays": [], "slots": ["10:30", "15:00", "20:30"],
        }])
    yield "s150"
    session.engine.dispose()


def test_store_without_saved_weather_uses_common_mock(store_s150):
    assert read_store_db.read_store_weather(store_s150) == []
    assert read_store_db.read_weather(store_s150) == read_store_db.read_weather()


def test_update_store_weather_saves_store_region_and_feeds_analysis(store_s150):
    summary = store_weather.update_store_weather(store_s150, client=FakeKma(missing_day=dt.date(2026, 11, 1)), now=NOW)
    assert summary["observed_days"] == 30 and summary["forecast_days"] == 4 and summary["location"]["nx"] == 73

    rows = {r["date"]: r for r in read_store_db.read_weather(store_s150)}
    partly = rows[dt.date(2026, 11, 1)]  # 기온·강수는 결측, 전운량만 있는 날: 결측 칸은 비워서 저장
    assert (partly["temp_max"], partly["precip_mm"], partly["precip_type"], partly["sky"]) == (None, None, None, "흐림")
    observed = rows[dt.date(2026, 11, 7)]
    assert (observed["kind"], observed["sky"], observed["precip_type"], float(observed["precip_mm"]), observed["issued_at"]) == ("observed", "흐림", "비", 12.5, None)
    tomorrow = rows[dt.date(2026, 11, 14)]
    assert (tomorrow["kind"], tomorrow["sky"], tomorrow["precip_type"], float(tomorrow["temp_max"]), tomorrow["pop_max"]) == ("forecast", "흐림", "비", 12.0, 70)
    assert tomorrow["issued_at"] == dt.datetime(2026, 11, 13, 8, 0, tzinfo=SEOUL)
    assert rows[dt.date(2026, 11, 15)]["precip_type"] == "비/눈"

    saved = store_weather.saved_weather(store_s150)
    assert saved["location"]["station"]["station_id"] == 101 and len(saved["days"]) == 30 + 4
    assert saved["days"][-1]["sky"] == "맑음"

    # 분석 입력: 그 가게 지역 날씨 (비 많이 온 날 12.5mm 은 비 날로 잡힌다), 모르는 값은 None
    weather = {w.date: w for w in build_analysis_inputs(store_s150, NOW).weather}
    assert weather[dt.date(2026, 11, 7)].rain_mm == 12.5 and weather[dt.date(2026, 11, 1)].temp_max is None


def test_next_day_save_replaces_forecast_with_observation_and_drops_stale_forecasts(store_s150):
    store_weather.update_store_weather(store_s150, client=FakeKma(), now=NOW)
    next_day = NOW + dt.timedelta(days=1)
    store_weather.update_store_weather(store_s150, client=FakeKma(missing_day=dt.date(2026, 11, 12)), now=next_day)
    rows = {r["date"]: r for r in read_store_db.read_store_weather(store_s150)}
    assert rows[dt.date(2026, 11, 13)]["kind"] == "observed"  # 어제 예보 → 관측으로 바뀜
    assert rows[dt.date(2026, 11, 12)]["kind"] == "observed"  # 오늘 받은 결측이 어제 받은 관측을 지우지 않는다
    assert all(r["kind"] == "observed" for d, r in rows.items() if d < next_day.date())  # 지난날 예보는 남지 않는다


def test_update_raises_when_nothing_could_be_read(store_s150):
    error = KmaAuthError("유효한 인증키가 아닙니다.")
    fake = FakeKma(errors={"stn_inf": error, "VilageFcst": error})
    with pytest.raises(Exception, match="인증키"):
        store_weather.update_store_weather(store_s150, client=fake, now=NOW)
    assert read_store_db.read_store_weather(store_s150) == []


# ── 매장 등록과 이어짐 ──


@pytest.fixture
def api(monkeypatch):
    from app.core.naver_place import PlaceInfo

    hours = {"open": "11:00", "close": "21:00"}
    info = PlaceInfo(place_id="123456", name="시험 가게", category="돈가스", road_address="강원 춘천시", address="강원 춘천시",
                     lat=CHUNCHEON[0], lng=CHUNCHEON[1], weekly_hours={d: hours for d in ("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN")}, break_time=None)
    monkeypatch.setattr(stores_router, "crawl_place", lambda place_id: info)
    monkeypatch.setattr(stores_router.registered_stores, "register", lambda info: "s101")
    monkeypatch.setattr(stores_router, "save_settings_changes", lambda sid, ch: None)
    monkeypatch.setattr(stores_router.demo_data, "fill", lambda *a, **k: {"orders": 0})
    fetched = []
    monkeypatch.setattr(store_weather, "update_store_weather", lambda sid: fetched.append(sid) or {})
    return TestClient(create_app()), fetched


def test_register_fetches_store_weather_in_background_when_key_is_set(api, monkeypatch):
    client, fetched = api
    monkeypatch.setattr(settings, "kma_api_key", "test-key")
    assert client.post("/api/stores/register", json={"place_id": "123456"}).json()["store_id"] == "s101"
    assert fetched == ["s101"]


def test_register_skips_weather_without_key(api):
    client, fetched = api
    assert client.post("/api/stores/register", json={"place_id": "123456"}).json()["store_id"] == "s101"
    assert fetched == []


def test_refresh_weather_explains_missing_key_and_mock_store():
    client = TestClient(create_app())
    assert client.post("/api/stores/s001/weather/refresh").json()["error"]["code"] == "NOT_REGISTERED_STORE"
    assert client.get("/api/stores/s001/weather").json()["days"] == []  # 목업 가게는 기상청 날씨가 없다


# ── 3시간마다 새로 받기 ──


def test_only_registered_stores_with_key_are_refreshed(monkeypatch):
    assert not store_weather.can_fetch("s101")  # 키 없음
    monkeypatch.setattr(settings, "kma_api_key", "test-key")
    assert store_weather.can_fetch("s101") and store_weather.can_fetch("s150")
    assert not store_weather.can_fetch("s001")  # 목업 가게
    assert not store_weather.can_fetch("s004")  # 목업 가게로 이은 피플스클럽


def test_store_is_due_three_hours_after_last_fetch(store_s150, monkeypatch):
    from app.weather import auto_refresh

    monkeypatch.setattr(settings, "kma_api_key", "test-key")
    assert auto_refresh.stores_due(NOW) == ["s150"]  # 받은 적 없음
    store_weather.update_store_weather(store_s150, client=FakeKma(), now=NOW)
    assert auto_refresh.stores_due(NOW + dt.timedelta(hours=2, minutes=59)) == []
    assert auto_refresh.stores_due(NOW + dt.timedelta(hours=3)) == ["s150"]


def test_refresh_due_refetches_and_skips_already_observed_days(store_s150, monkeypatch):
    from app.weather import auto_refresh

    monkeypatch.setattr(settings, "kma_api_key", "test-key")
    store_weather.update_store_weather(store_s150, client=FakeKma(), now=NOW)
    later, fake = NOW + dt.timedelta(hours=3), FakeKma(short_no_data_bases=())
    real_update = store_weather.update_store_weather
    monkeypatch.setattr(store_weather, "update_store_weather", lambda sid: real_update(sid, client=fake, now=later))
    invalidated = []
    monkeypatch.setattr(auto_refresh, "save_settings_changes", lambda sid, ch: invalidated.append(sid))

    assert auto_refresh.refresh_due(later) == ["s150"] and invalidated == ["s150"]
    daily_calls = [p for p, params in fake.calls if p.endswith("kma_sfcdd.php")]
    assert len(daily_calls) == 1  # 저장해 둔 29일은 건너뛰고 어제만 다시 부른다
    fetch = read_store_db.read_store_weather_fetch(store_s150)
    assert fetch["fetched_at"] == later and fetch["payload"]["metadata"]["short_forecast_issued_at"] == "2026-11-13T14:00:00+09:00"  # 17:05 기준 최신 발표
    assert len(read_store_db.read_store_weather(store_s150)) == 30 + 4  # 관측은 그대로 남는다


def test_refresh_store_failure_is_logged_not_raised(monkeypatch):
    from app.weather import auto_refresh

    def fail(sid):
        raise KmaAuthError("유효한 인증키가 아닙니다.")

    monkeypatch.setattr(store_weather, "update_store_weather", fail)
    assert auto_refresh.refresh_store("s150") is False
