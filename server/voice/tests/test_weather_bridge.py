"""음성 백엔드가 메인 서버의 기상청 날씨 DB를 읽기 (voice/weather.py, 에이전트 조직 개편 4단계)."""

import datetime as dt
from decimal import Decimal

from voice import weather
from voice.context import load
from voice.tests.conftest import Donna, choongjang

ROWS = [
    {"date": dt.date(2026, 11, 16), "kind": "observed", "temp_min": Decimal("2.1"), "temp_max": Decimal("11.0"), "sky": "맑음",
     "precip_type": "없음", "precip_mm": None, "pop_max": None},
    {"date": dt.date(2026, 11, 17), "kind": "forecast", "temp_min": Decimal("3.0"), "temp_max": Decimal("9.0"), "sky": "흐림",
     "precip_type": "비", "precip_mm": Decimal("6.0"), "pop_max": 70},
    {"date": dt.date(2026, 11, 18), "kind": "forecast", "temp_min": Decimal("1.0"), "temp_max": Decimal("8.0"), "sky": "구름많음",
     "precip_type": "없음", "precip_mm": Decimal("0"), "pop_max": 20},
]
HOURLY = [{"datetime": f"2026-11-17T{h:02d}:00:00+09:00", "precipitation_type": "비" if h >= 14 else "없음",
           "precipitation_probability": 70 if h >= 14 else 30} for h in range(24)]
FETCH = {"fetched_at": None, "payload": {"forecasts": {"hourly": HOURLY}}}


def test_convert_maps_fields_and_rain_start():
    days = weather.convert(ROWS, FETCH)
    assert days[0] == {"date": "2026-11-16", "temp_min": 2.1, "temp_max": 11.0, "rain_mm": 0.0, "rain_chance": 0.0, "label": "맑음"}
    assert days[1] == {"date": "2026-11-17", "temp_min": 3.0, "temp_max": 9.0, "rain_mm": 6.0, "rain_chance": 0.7, "label": "비",
                       "rain_from": 14}
    assert days[2]["label"] == "구름" and days[2]["rain_chance"] == 0.2 and "rain_from" not in days[2]


def test_observed_rain_counts_as_certain():
    rained = {**ROWS[0], "precip_type": "비", "precip_mm": Decimal("3.5")}
    assert weather.convert([rained], None)[0]["rain_chance"] == 1.0


def baseline() -> Donna:
    donna = Donna()
    donna.client.post("/v1/dev/fixtures", json={"fixture": "s001_baseline"})  # 시연 가게가 아닌 시험 가게
    return donna


def test_non_demo_store_reads_db(monkeypatch):
    baseline()
    monkeypatch.setattr(weather, "from_db", lambda store_id: weather.convert(ROWS, FETCH))
    assert [w["date"] for w in load("s001").data["weather"]] == ["2026-11-16", "2026-11-17", "2026-11-18"]


def test_demo_store_keeps_scenario_weather(monkeypatch):
    choongjang(at=None)
    monkeypatch.setattr(weather, "from_db", lambda store_id: (_ for _ in ()).throw(AssertionError("시연 가게는 DB 를 읽지 않는다")))
    rain = next(w for w in load("s005").data["weather"] if w["date"] == "2026-11-17")
    assert rain["rain_from"] == 14 and rain["rain_chance"] == 0.7  # 픽스처 그대로


def test_no_db_weather_keeps_fixture():
    baseline()
    assert load("s001").data["weather"] and weather.from_db("s001") is None  # 목업 가게는 기상청 날씨를 받지 않는다
