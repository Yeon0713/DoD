"""사장님이 등록한 가게 (네이버 지도에서 찾아 "우리 가게 맞아요"를 누른 실제 가게).

- 등록할 때 네이버 지도에서 한 번 읽은 가게 정보(app/core/naver_place.py)를 DB 에 저장한다. 평소에는 DB 를 쓰고,
  사장님이 "다시 불러오기"를 누를 때만 다시 읽는다.
- 가게마다 기존 목업 가게(s001~s003)와 같은 모양의 가게 파일을 만든다: db/data/s101.db, s102.db ...
  (가게 정보와 메뉴만 들어 있고, 주문·알바는 없다. 리뷰는 리뷰 불러오기로 채운다)
- 등록 기록은 db/app_data/registry.db 에 둔다. 목업 생성기(db/mock/generate.py)는 db/data 의 *.db 를 지우고 다시 만들므로
  등록 기록은 그 밖에 둔다. 생성기를 다시 돌리면 등록한 가게 파일(s101.db ...)은 지워지니 다시 등록해야 한다.

표
  stores(store_id, place_id, info_json, crawled_at, registered_at)   등록한 가게와 네이버에서 읽은 정보
  owners(owner_key, store_id)                                          로그인 계정 → 가게 (예: "naver:<네이버 회원 번호>")
  review_platforms(store_id, review_id, platform, imported_at)        불러온 리뷰가 어느 플랫폼 것인지 (가게 파일 reviews 표에는 플랫폼 칸이 없다)
"""

import datetime as dt
import json
import sqlite3
from collections import Counter
from pathlib import Path

from sqlalchemy import insert, select, update
from sqlalchemy.schema import CreateIndex, CreateTable

from app.core.naver_place import PlaceInfo
from app.core.seoul_time import now_seoul
from db import models
from db.session import DATA_DIR, engine, store_engine

REGISTRY_PATH = Path(__file__).resolve().parents[2] / "db" / "app_data" / "registry.db"
FIRST_NUMBER = 101  # s001~s099 는 목업 가게 자리
# 목업 생성기가 1년치 데이터를 만들어 둔 실제 가게: 네이버 가게 id → 목업 가게 id.
# 이 가게를 등록하면 새 파일을 만들지 않고 목업 가게로 잇는다 (목업 파일은 고치지 않고 등록 기록만 남긴다).
MOCK_PLACES = {"1909851296": "s004"}  # 피플스클럽


def is_mock_store(store_id: str) -> bool:
    return store_id in MOCK_PLACES.values()


def _db() -> sqlite3.Connection:
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(REGISTRY_PATH)
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS stores (store_id TEXT PRIMARY KEY, place_id TEXT UNIQUE NOT NULL,
            info_json TEXT NOT NULL, crawled_at TEXT NOT NULL, registered_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS owners (owner_key TEXT PRIMARY KEY, store_id TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS review_platforms (store_id TEXT NOT NULL, review_id INTEGER NOT NULL,
            platform TEXT NOT NULL, imported_at TEXT NOT NULL, PRIMARY KEY (store_id, review_id));
        """
    )
    return conn


def store_for_place(place_id: str) -> str | None:
    with _db() as conn:
        row = conn.execute("SELECT store_id FROM stores WHERE place_id = ?", (place_id,)).fetchone()
    return row[0] if row else None


def store_for_owner(owner_key: str) -> str | None:
    """그 계정이 등록해 둔 가게. 가게 파일이 없어졌으면(목업 생성기를 다시 돌림) 없는 것으로 본다."""
    with _db() as conn:
        row = conn.execute("SELECT store_id FROM owners WHERE owner_key = ?", (owner_key,)).fetchone()
    return row[0] if row and (DATA_DIR / f"{row[0]}.db").exists() else None


def set_owner(owner_key: str, store_id: str) -> None:
    with _db() as conn:
        conn.execute("INSERT INTO owners VALUES (?, ?) ON CONFLICT(owner_key) DO UPDATE SET store_id = excluded.store_id", (owner_key, store_id))


def place_info(store_id: str) -> PlaceInfo | None:
    """등록한 가게면 네이버 지도에서 읽어 둔 정보, 아니면(목업 가게) None."""
    with _db() as conn:
        row = conn.execute("SELECT info_json FROM stores WHERE store_id = ?", (store_id,)).fetchone()
    return PlaceInfo.from_dict(json.loads(row[0])) if row else None


def _hhmm(value: str) -> dt.time:
    hour, minute = map(int, value.split(":"))
    return dt.time(hour % 24, minute)


def _minus(value: str, minutes: int) -> str:
    hour, minute = map(int, value.split(":"))
    total = (hour * 60 + minute - minutes) % 1440
    return f"{total // 60:02d}:{total % 60:02d}"


def store_row(store_id: str, info: PlaceInfo) -> dict:
    """가게 파일 store 표 한 줄. 대표 영업시간은 여는 요일에서 가장 흔한 시간, 쉬는 요일은 영업시간이 없는 요일."""
    open_days = [hours for hours in info.weekly_hours.values() if hours]
    if open_days:
        open_time, close_time = Counter((h["open"], h["close"]) for h in open_days).most_common(1)[0][0]
    else:
        open_time, close_time = "11:00", "21:00"
    # 알림 세 시각: 출근 후(문 열기 30분 전), 점심 장사 끝나고(브레이크 시작 30분 뒤, 없으면 15:00), 마감 전(닫기 30분 전)
    opening, closing = _minus(open_time, 30), _minus(close_time, 30)
    afternoon = _minus(info.break_time["start"], -30) if info.break_time else "15:00"
    if not opening < afternoon < closing:
        afternoon = _minus(closing, 120) if opening < _minus(closing, 120) else closing
    return {
        "store_id": store_id,
        "name": info.name,
        "category": info.category or "음식점",
        "address": info.road_address or info.address,
        "lat": info.lat,
        "lng": info.lng,
        "open_time": _hhmm(open_time),
        "close_time": _hhmm(close_time),
        "closed_weekdays": [code for code, hours in info.weekly_hours.items() if hours is None],
        "slots": [opening, afternoon, closing],
    }


DRINK_WORDS = ("콜라", "사이다", "음료", "맥주", "소주", "하이볼", "에이드", "주스", "커피", "물")


def _menu_rows(info: PlaceInfo) -> list[dict]:
    """메뉴 표 category 는 main, side, drink 중 하나다 (DB 규칙). 음료 이름이면 drink, 나머지는 main."""
    return [
        {"menu_id": number, "name": menu.name, "category": "drink" if any(w in menu.name for w in DRINK_WORDS) else "main", "price": menu.price or 0}
        for number, menu in enumerate(info.menus, start=1)
    ]


def _next_store_id() -> str:
    used = {path.stem for path in DATA_DIR.glob("s[0-9][0-9][0-9].db")}
    number = FIRST_NUMBER
    while f"s{number:03d}" in used:
        number += 1
    return f"s{number:03d}"


def _create_store_file(store_id: str) -> None:
    (DATA_DIR / f"{store_id}.db").touch()
    engine.dispose()  # 새 연결이 새 가게 파일을 붙이게 한다 (db/session.py 는 연결할 때 가게 파일을 붙인다)
    tables = [models.Base.metadata.tables[f"{models.STORE_SCHEMA}.{name}"] for name in models.STORE_TABLES]
    with store_engine(store_id).begin() as conn:
        for table in tables:
            conn.execute(CreateTable(table))
            for index in sorted(table.indexes, key=lambda i: i.name):
                conn.execute(CreateIndex(index))


def register(info: PlaceInfo) -> str:
    """가게를 등록한다. 이미 등록한 가게(같은 네이버 가게 id)면 정보만 새로 고치고 같은 가게 id 를 돌려준다."""
    now = now_seoul().isoformat()
    mock = MOCK_PLACES.get(info.place_id)
    if mock and (DATA_DIR / f"{mock}.db").exists():
        _save_place(mock, info, now)
        return mock
    existing = store_for_place(info.place_id)
    if existing and (DATA_DIR / f"{existing}.db").exists():
        refresh(existing, info)
        return existing
    store_id = existing or _next_store_id()
    _create_store_file(store_id)
    try:
        with store_engine(store_id).begin() as conn:
            conn.execute(insert(models.Store), [store_row(store_id, info)])
            if info.menus:
                conn.execute(insert(models.Menu), _menu_rows(info))
    except Exception:
        # 반쯤 만든 가게 파일을 남기지 않는다
        engine.dispose()
        (DATA_DIR / f"{store_id}.db").unlink(missing_ok=True)
        raise
    _save_place(store_id, info, now)
    return store_id


def _save_place(store_id: str, info: PlaceInfo, now: str) -> None:
    with _db() as conn:
        conn.execute(
            "INSERT INTO stores VALUES (?, ?, ?, ?, ?) ON CONFLICT(store_id) DO UPDATE SET info_json = excluded.info_json, crawled_at = excluded.crawled_at",
            (store_id, info.place_id, json.dumps(info.to_dict(), ensure_ascii=False), now, now),
        )


def refresh(store_id: str, info: PlaceInfo) -> None:
    """네이버 지도에서 다시 읽은 정보로 가게와 메뉴를 고친다.

    메뉴는 지우지 않는다 (주문 기록이 메뉴를 가리킨다). 이름이 같은 메뉴는 가격만 고치고, 새 메뉴만 더한다.
    목업 가게(MOCK_PLACES)는 생성기가 만든 파일을 고치지 않고 등록 기록만 새로 고친다.
    """
    if is_mock_store(store_id):
        _save_place(store_id, info, now_seoul().isoformat())
        return
    row = store_row(store_id, info)
    with store_engine(store_id).begin() as conn:
        conn.execute(update(models.Store).where(models.Store.store_id == store_id).values(**{k: v for k, v in row.items() if k != "store_id"}))
        existing = {r.name: r.menu_id for r in conn.execute(select(models.Menu.name, models.Menu.menu_id))}
        next_id = max(existing.values(), default=0) + 1
        for menu in _menu_rows(info):
            if menu["name"] in existing:
                conn.execute(update(models.Menu).where(models.Menu.menu_id == existing[menu["name"]]).values(price=menu["price"], category=menu["category"]))
            else:
                conn.execute(insert(models.Menu), [{**menu, "menu_id": next_id}])
                next_id += 1
    with _db() as conn:
        conn.execute("UPDATE stores SET info_json = ?, crawled_at = ? WHERE store_id = ?", (json.dumps(info.to_dict(), ensure_ascii=False), now_seoul().isoformat(), store_id))


def review_platforms(store_id: str) -> dict[int, str]:
    """불러온 리뷰 번호 → 플랫폼 (BAEMIN, NAVER, COUPANG)"""
    with _db() as conn:
        return dict(conn.execute("SELECT review_id, platform FROM review_platforms WHERE store_id = ?", (store_id,)).fetchall())


def imported_counts(store_id: str) -> dict[str, int]:
    with _db() as conn:
        rows = conn.execute("SELECT platform, COUNT(*) FROM review_platforms WHERE store_id = ? GROUP BY platform", (store_id,)).fetchall()
    return dict(rows)


def add_reviews(store_id: str, platform: str, rows: list[dict]) -> int:
    """리뷰를 가게 파일 reviews 표에 넣고 플랫폼을 기록한다. rows 칸: written_at, rating, content, complaint_type"""
    if not rows:
        return 0
    with store_engine(store_id).begin() as conn:
        last = conn.execute(models.Review.__table__.select().with_only_columns(models.Review.review_id).order_by(models.Review.review_id.desc()).limit(1)).scalar()
        start = (last or 0) + 1
        values = [{"review_id": start + i, "order_id": None, "customer_key": row.get("customer_key"), **{k: v for k, v in row.items() if k != "customer_key"}} for i, row in enumerate(rows)]
        conn.execute(insert(models.Review), values)
    return mark_platform(store_id, platform, [v["review_id"] for v in values])


def mark_platform(store_id: str, platform: str, review_ids: list[int]) -> int:
    """가게 파일에 이미 있는 리뷰가 어느 플랫폼 것인지 기록한다. 기록한 수를 돌려준다."""
    imported_at = now_seoul().isoformat()
    with _db() as conn:
        conn.executemany("INSERT INTO review_platforms VALUES (?, ?, ?, ?)", [(store_id, review_id, platform, imported_at) for review_id in review_ids])
    return len(review_ids)


def reset_all() -> list[str]:
    """시험용 초기화: 등록한 가게 파일(s101 ...)과 등록 기록을 모두 지운다. 목업 가게(s001~s099)는 건드리지 않는다.

    지운 가게 id 를 돌려준다.
    """
    engine.dispose()  # 열린 연결이 지울 파일을 붙잡고 있지 않게
    removed = []
    for path in sorted(DATA_DIR.glob("s[0-9][0-9][0-9].db")):
        if int(path.stem[1:]) >= FIRST_NUMBER:
            path.unlink(missing_ok=True)
            removed.append(path.stem)
    REGISTRY_PATH.unlink(missing_ok=True)
    engine.dispose()
    return removed
