"""시험 주간 데이터: 팀 목업 가게 파일을 고치지 않고 그 위에 겹쳐 읽는 시험용 행.

파일: server/db/test_scenarios/<가게>.json (git 에 올라간다. 만드는 스크립트도 같은 폴더, 설명은 docs/test-week.md)
  week      시험 주간 {"start", "end"} (앱 ☰ "시험 날짜"가 이 주의 알림 시각을 보여 준다)
  weather   그날 날씨를 이 값으로 바꾼다 (목업 날씨·기상청 날씨보다 앞선다)
  events    그 가게에만 보이는 행사 (공통 행사 표에 더한다)
  orders    더할 주문 (items: 주문 메뉴)
  reviews   더할 리뷰 (order_id 가 있으면 가게 파일이나 이 파일의 주문과 잇는다)
  reservations  네이버 예약에서 받아 온 것처럼 넣는 예약 (app/data_pipeline/reservations.py 의 sync_from_naver)

read_store_db 의 읽기 함수가 이 행을 더해 돌려준다. 그래서 분석·계획·매출·리뷰 화면이 모두 같은 데이터를 본다.
파일이 없는 가게는 아무것도 바뀌지 않는다.
"""

import datetime as dt
import json
from functools import lru_cache
from pathlib import Path

from app.core.seoul_time import SEOUL

SCENARIO_DIR = Path(__file__).resolve().parents[2] / "db" / "test_scenarios"


def path_of(store_id: str) -> Path:
    return SCENARIO_DIR / f"{store_id}.json"


def _time(text: str) -> dt.datetime:
    return dt.datetime.fromisoformat(text).astimezone(SEOUL)


@lru_cache(maxsize=16)
def _load(path: str, mark: float) -> dict:
    """파일을 읽어 시각·날짜를 DB 에서 읽은 행과 같은 모양으로 바꾼다. mark(고친 시각)가 바뀌면 다시 읽는다."""
    with open(path, encoding="utf-8") as f:
        doc = json.load(f)
    doc["weather"] = [{**w, "date": dt.date.fromisoformat(w["date"])} for w in doc.get("weather", [])]
    doc["events"] = [{**e, "starts_at": _time(e["starts_at"]), "ends_at": _time(e["ends_at"])} for e in doc.get("events", [])]
    doc["orders"] = [{**o, "ordered_at": _time(o["ordered_at"])} for o in doc.get("orders", [])]
    doc["reviews"] = [{**r, "written_at": _time(r["written_at"])} for r in doc.get("reviews", [])]
    return doc


def scenario(store_id: str | None) -> dict | None:
    """그 가게의 시험 주간 데이터. 없으면 None"""
    if not store_id:
        return None
    path = path_of(store_id)
    if not path.exists():
        return None
    return _load(str(path), path.stat().st_mtime)


def mark(store_id: str) -> str:
    """파일 지문 (계산 결과를 기억하는 곳이 파일이 바뀐 것을 알게)"""
    path = path_of(store_id)
    return f"{path.stat().st_size}:{path.stat().st_mtime_ns}" if path.exists() else "-"


def week(store_id: str) -> tuple[dt.date, dt.date] | None:
    doc = scenario(store_id)
    if not doc or "week" not in doc:
        return None
    return dt.date.fromisoformat(doc["week"]["start"]), dt.date.fromisoformat(doc["week"]["end"])


def _in(at: dt.datetime, until: dt.datetime, since: dt.datetime | None) -> bool:
    return at <= until and (since is None or at >= since)


def orders(store_id: str, until: dt.datetime, since: dt.datetime | None = None) -> list[dict]:
    doc = scenario(store_id)
    if not doc:
        return []
    return [{k: v for k, v in o.items() if k != "items"} for o in doc["orders"] if _in(o["ordered_at"], until, since)]


def order_items(store_id: str, until: dt.datetime, since: dt.datetime | None = None) -> list[dict]:
    doc = scenario(store_id)
    if not doc:
        return []
    return [{"order_id": o["order_id"], **item} for o in doc["orders"] if _in(o["ordered_at"], until, since) for item in o.get("items", [])]


def reviews(store_id: str, until: dt.datetime, order_info) -> list[dict]:
    """더할 리뷰. order_info(order_ids) → {order_id: (channel, ordered_at)} 로 가게 파일의 주문과 잇는다."""
    doc = scenario(store_id)
    if not doc:
        return []
    rows = [dict(r) for r in doc["reviews"] if r["written_at"] <= until]
    own = {o["order_id"]: (o["channel"], o["ordered_at"]) for o in doc["orders"]}
    wanted = {r["order_id"] for r in rows if r.get("order_id") and r["order_id"] not in own}
    linked = {**(order_info(wanted) if wanted else {}), **own}
    for row in rows:
        channel, ordered_at = linked.get(row.get("order_id"), (None, None))
        row["order_channel"], row["ordered_at"] = channel, ordered_at
    return rows


def events(store_id: str | None) -> list[dict]:
    doc = scenario(store_id)
    return list(doc["events"]) if doc else []


def weather(store_id: str | None, rows: list[dict]) -> list[dict]:
    """날씨 행에 시험 날씨를 덮어쓴다 (같은 날짜는 시험 값)."""
    doc = scenario(store_id)
    if not doc or not doc["weather"]:
        return rows
    days = {w["date"] for w in doc["weather"]}
    return sorted([r for r in rows if r["date"] not in days] + list(doc["weather"]), key=lambda r: r["date"])
