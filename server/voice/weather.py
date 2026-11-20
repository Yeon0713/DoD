"""기상청 날씨를 음성 백엔드 모양으로 읽는다 (에이전트 조직 개편 4단계, donna-voice/docs/agent-org-plan.md 4-2).

메인 서버(app/weather/auto_refresh.py)가 매일 자정에 받아 둔 가게 날씨 DB를 읽기만 한다. 기상청을 직접 부르지 않는다.
  store_weather_daily  날짜마다 한 줄 (지난날 관측, 오늘부터 예보)
  store_weather_fetch  마지막으로 받은 전체 결과. 시간별 예보(비 시작 시각)는 여기에만 있다
음성 백엔드 모양 (fixtures 의 weather 와 같다): {date, temp_min, temp_max, rain_mm, rain_chance(0~1), rain_from(시), label}
날씨를 받을 수 없는 가게(목업 가게, 기상청 키 없음)는 None 이고, 부르는 쪽(context.load)이 픽스처 날씨를 그대로 쓴다.
"""

import datetime as dt

RAIN_TYPES = {"비", "소나기", "비/눈"}
RAIN_CHANCE = 60  # 시간별 강수확률이 이 이상이면 비가 오는 시각으로 본다 (브리핑의 rain_today 0.6 과 같다)


def _num(value) -> float | None:
    return None if value is None else float(value)


def _label(row: dict) -> str:
    if row.get("precip_type") in RAIN_TYPES:
        return "비"
    if row.get("precip_type") == "눈":
        return "눈"
    return {"구름많음": "구름"}.get(row.get("sky") or "", row.get("sky") or "맑음")


def _rain_from(hourly: list[dict], day: str) -> int | None:
    """그날 처음 비가 오는 시각(시). 비가 없거나 시간별 예보가 없으면 None."""
    for hour in sorted((h for h in hourly if h["datetime"][:10] == day), key=lambda h: h["datetime"]):
        if (hour.get("precipitation_type") or "없음") != "없음" or (hour.get("precipitation_probability") or 0) >= RAIN_CHANCE:
            return int(hour["datetime"][11:13])
    return None


def convert(rows: list[dict], fetch: dict | None) -> list[dict]:
    hourly = ((fetch or {}).get("payload") or {}).get("forecasts", {}).get("hourly") or []
    days = []
    for row in sorted(rows, key=lambda r: r["date"]):
        day = row["date"].isoformat() if isinstance(row["date"], dt.date) else str(row["date"])
        if row.get("pop_max") is not None:
            chance = row["pop_max"] / 100
        else:  # 관측 줄은 강수확률이 없다. 실제로 비가 왔으면 1
            chance = 1.0 if row.get("precip_type") in RAIN_TYPES else 0.0
        item = {"date": day, "temp_min": _num(row.get("temp_min")), "temp_max": _num(row.get("temp_max")),
                "rain_mm": _num(row.get("precip_mm")) or 0.0, "rain_chance": chance, "label": _label(row)}
        start = _rain_from(hourly, day)
        if start is not None:
            item["rain_from"] = start
        days.append(item)
    return days


def from_db(store_id: str) -> list[dict] | None:
    """메인 서버가 받아 둔 그 가게 날씨. 받을 수 없는 가게거나 아직 받은 적이 없으면 None."""
    from app.data_pipeline import read_store_db
    from app.weather import store_weather

    if not store_weather.can_fetch(store_id):
        return None
    rows = read_store_db.read_store_weather(store_id)
    return convert(rows, read_store_db.read_store_weather_fetch(store_id)) if rows else None
