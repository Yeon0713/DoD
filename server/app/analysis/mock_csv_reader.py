"""목업 CSV(server/db/mock/out/*.csv)를 분석 입력(AnalysisInputs)으로 바꾼다.

- 코드값은 대문자로 바꾼다. 예) hall → HALL, main → MAIN
- 행사·경기 id 는 문자열로 바꾼다. 예) 1 → event_001, game_001
- 행사·경기 종류는 계약 코드값으로 바꾼다. 모르는 행사 종류는 LOCAL_EVENT 로 남기고(행사는 종류와 관계없이
  특별한 칸이다), 모르는 경기 종목은 GameKind 에 맞는 값이 없어 건너뛴다. 둘 다 경고를 남긴다.
- 목업 매장의 dayparts 는 예전 시간대(점심·저녁·야간)라 읽지 않는다. 분석은 기본 경계를 쓴다.
- 리뷰 id 는 rv_001 형식, 본문(content)은 text 로 옮긴다. 목업에 리뷰 플랫폼 열이 없어서
  주문과 이어진 리뷰는 BAEMIN, 나머지는 NAVER 로 채운다(임시값). 분류 결과(label)는 비워 둔다.
"""

import csv
import datetime as dt
import json
import logging
from pathlib import Path

from app.analysis.input_shapes import (
    AnalysisInputs,
    Menu,
    Order,
    OrderItem,
    Shift,
    StoreInfo,
    WeatherDay,
)
from app.planner.data_shapes import Event, EventKind, Game, GameKind, Review

logger = logging.getLogger(__name__)

# server/app/analysis/ 에서 두 단계 위가 server/
MOCK_DIR = Path(__file__).resolve().parents[2] / "db" / "mock" / "out"

EVENT_KINDS: dict[str, EventKind] = {
    "univ_festival": "UNIV_FESTIVAL",
    "local_festival": "LOCAL_FESTIVAL",
    "marathon": "MARATHON",
    "other": "LOCAL_EVENT",
}


SPORT_KINDS: dict[str, GameKind] = {"baseball": "BASEBALL", "soccer": "FOOTBALL", "esports": "ESPORTS"}


def event_kind(kind: str) -> EventKind:
    """목업 행사 종류 → 계약 코드값. 모르는 종류는 LOCAL_EVENT 로 남긴다."""
    if kind not in EVENT_KINDS:
        logger.warning("모르는 행사 종류 %r 을 LOCAL_EVENT 로 읽었다", kind)
        return "LOCAL_EVENT"
    return EVENT_KINDS[kind]


def game_kind(sport: str, level: str) -> GameKind | None:
    """(종목, 수준) → 경기 종류. 국가대표는 종목과 관계없이 NATIONAL_TEAM 이다. 모르는 종목은 None."""
    if level == "national":
        return "NATIONAL_TEAM"
    return SPORT_KINDS.get(sport)


def _rows(directory: Path, table: str) -> list[dict]:
    with (directory / f"{table}.csv").open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _or_none(value: str) -> str | None:
    return value or None


def read_mock_csv(directory: Path = MOCK_DIR) -> AnalysisInputs:
    store = _rows(directory, "store")[0]
    wages = {row["staff_id"]: int(row["hourly_wage"]) for row in _rows(directory, "staff")}
    return AnalysisInputs(
        store=StoreInfo(
            store_id=store["store_id"],
            name=store["name"],
            lat=float(store["lat"]),
            lng=float(store["lng"]),
            open_time=dt.time.fromisoformat(store["open_time"]),
            close_time=dt.time.fromisoformat(store["close_time"]),
            closed_weekdays=json.loads(store["closed_weekdays"] or "[]"),
        ),
        orders=[
            Order(
                order_id=row["order_id"],
                ordered_at=dt.datetime.fromisoformat(row["ordered_at"]),
                channel=row["channel"].upper(),
                customer_key=_or_none(row["customer_key"]),
                total_amount=int(row["total_amount"]),
            )
            for row in _rows(directory, "orders")
        ],
        order_items=[
            OrderItem(
                order_id=row["order_id"],
                menu_id=row["menu_id"],
                quantity=int(row["quantity"]),
                unit_price=int(row["unit_price"]),
            )
            for row in _rows(directory, "order_items")
        ],
        menus=[
            Menu(
                menu_id=row["menu_id"],
                name=row["name"],
                category=row["category"].upper(),
                price=int(row["price"]),
                unit_cost=int(row["unit_cost"]) if row.get("unit_cost") else None,
            )
            for row in _rows(directory, "menu")
        ],
        shifts=[
            Shift(
                shift_id=row["shift_id"],
                staff_key=f"staff_{int(row['staff_id']):03d}",
                starts_at=dt.datetime.fromisoformat(row["starts_at"]),
                ends_at=dt.datetime.fromisoformat(row["ends_at"]),
                hourly_wage=wages[row["staff_id"]],
            )
            for row in _rows(directory, "shifts")
        ],
        events=[
            Event(
                event_id=f"event_{int(row['event_id']):03d}",
                kind=event_kind(row["kind"]),
                title=row["name"],
                start_at=dt.datetime.fromisoformat(row["starts_at"]),
                end_at=dt.datetime.fromisoformat(row["ends_at"]),
                distance_km=float(row["distance_km"]),
            )
            for row in _rows(directory, "events")
        ],
        games=_games(directory),
        weather=[
            WeatherDay(
                date=dt.date.fromisoformat(row["date"]),
                temp_max=float(row["temp_max"]),
                temp_min=float(row["temp_min"]),
                rain_mm=float(row["precip_mm"]),
            )
            for row in _rows(directory, "weather_daily")
        ],
        reviews=[
            Review(
                review_id=f"rv_{int(row['review_id']):03d}",
                platform="BAEMIN" if row["order_id"] else "NAVER",
                written_at=dt.datetime.fromisoformat(row["written_at"]),
                rating=int(row["rating"]),
                text=row["content"],
                customer_key=_or_none(row["customer_key"]),
                order_id=_or_none(row["order_id"]),
            )
            for row in _rows(directory, "reviews")
        ],
    )


def _games(directory: Path) -> list[Game]:
    games = []
    for row in _rows(directory, "games"):
        kind = game_kind(row["sport"], row["level"])
        if kind is None:
            logger.warning("모르는 경기 종목 %r (game_id=%s) 은 건너뛴다", row["sport"], row["game_id"])
            continue
        games.append(
            Game(
                game_id=f"game_{int(row['game_id']):03d}",
                kind=kind,
                title=row["title"],
                start_at=dt.datetime.fromisoformat(row["starts_at"]),
            )
        )
    return games
