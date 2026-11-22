"""예약·단체 주문. 손님은 도나를 쓰지 않으므로 네이버 예약(네이버 플레이스)에서 동기화한다고 보고, 사장님이 전화로 받은 것은 앱에서 직접 적는다.

기록: 등록 기록 DB(db/app_data/registry.db)의 reservations 표
  source   NAVER(네이버 예약에서 동기화) | OWNER(사장님이 직접 적음)
  kind     RESERVATION(방문 예약) | GROUP_ORDER(단체 주문, 포장·배달 포함)
  status   REQUESTED(예약 문의, 사장님이 받을지 정해야 함) | CONFIRMED(확정) | DECLINED(어렵다고 답함) | CANCELED(사장님이 지움)
  at       방문(또는 받아 갈) 시각 ISO, people 인원(단체 주문은 몇 인분)

네이버 예약 동기화는 지금 목업이다: 시험 주간 데이터(db/test_scenarios/<가게>.json)의 reservations 를
네이버에서 받아 온 것처럼 넣는다(external_id 로 한 번만). 진짜 네이버 예약 API 가 생기면 sync_from_naver 만 바꾼다.

확정한 예약은 이번 주 달력의 그 시간대 예상 매출에 "인원 × 1인 평균 금액"으로 더한다 (reservation_effect.py).
"""

import datetime as dt
import sqlite3

from app.core.seoul_time import now_seoul, to_seoul
from app.data_pipeline import registered_stores, test_scenario

KINDS = ("RESERVATION", "GROUP_ORDER")
STATUSES = ("REQUESTED", "CONFIRMED", "DECLINED", "CANCELED")
# 바꿀 수 있는 상태: 문의는 받거나 어렵다고 답하고, 확정한 것은 사장님이 직접 적은 것만 지운다 (같은 상태로 다시 누르는 것은 그대로 둔다)
CHANGES = {("REQUESTED", "CONFIRMED"), ("REQUESTED", "DECLINED"), ("CONFIRMED", "CANCELED")}
COLUMNS = ("reservation_id", "store_id", "source", "external_id", "kind", "at", "people", "name", "memo", "status", "created_at", "updated_at")


class ReservationError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _db() -> sqlite3.Connection:
    conn = registered_stores._db()
    conn.execute(
        """CREATE TABLE IF NOT EXISTS reservations (
            reservation_id INTEGER PRIMARY KEY AUTOINCREMENT, store_id TEXT NOT NULL,
            source TEXT NOT NULL CHECK (source IN ('NAVER', 'OWNER')), external_id TEXT,
            kind TEXT NOT NULL CHECK (kind IN ('RESERVATION', 'GROUP_ORDER')), at TEXT NOT NULL,
            people INTEGER NOT NULL CHECK (people > 0), name TEXT NOT NULL DEFAULT '', memo TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL CHECK (status IN ('REQUESTED', 'CONFIRMED', 'DECLINED', 'CANCELED')),
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE (store_id, external_id))"""
    )
    return conn


def _row(values) -> dict:
    row = dict(zip(COLUMNS, values))
    row["at"] = to_seoul(dt.datetime.fromisoformat(row["at"]))
    return row


def sync_from_naver(store_id: str) -> int:
    """네이버 예약에서 새로 들어온 예약을 넣는다 (목업: 시험 주간 데이터). 이미 넣은 것(external_id)은 건너뛴다. 넣은 수"""
    doc = test_scenario.scenario(store_id)
    items = (doc or {}).get("reservations") or []
    if not items:
        return 0
    now = now_seoul().isoformat()
    added = 0
    with _db() as conn:
        for item in items:
            cur = conn.execute(
                "INSERT OR IGNORE INTO reservations (store_id, source, external_id, kind, at, people, name, memo, status, created_at, updated_at) "
                "VALUES (?, 'NAVER', ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (store_id, item["external_id"], item["kind"], item["at"], item["people"], item.get("name", ""), item.get("memo", ""), item["status"], now, now),
            )
            added += cur.rowcount
    return added


def list_reservations(store_id: str, start: dt.date | None = None, end: dt.date | None = None, *, sync: bool = True) -> list[dict]:
    """그 가게 예약 (시각 순). start~end(양 끝 포함) 날짜만. 지운 것(CANCELED)은 빼고 돌려준다."""
    if sync:
        sync_from_naver(store_id)
    with _db() as conn:
        rows = [_row(r) for r in conn.execute(f"SELECT {', '.join(COLUMNS)} FROM reservations WHERE store_id = ? AND status != 'CANCELED'", (store_id,))]
    rows = [r for r in rows if (start is None or r["at"].date() >= start) and (end is None or r["at"].date() <= end)]
    return sorted(rows, key=lambda r: r["at"])


def add(store_id: str, at: dt.datetime, people: int, kind: str = "RESERVATION", name: str = "", memo: str = "") -> dict:
    """사장님이 직접 적은 예약 (전화로 받은 것). 바로 확정이다."""
    if kind not in KINDS:
        raise ReservationError("BAD_KIND", "예약 종류를 다시 골라 주세요")
    if not 1 <= people <= 500:
        raise ReservationError("BAD_PEOPLE", "인원을 다시 적어 주세요")
    now = now_seoul().isoformat()
    with _db() as conn:
        cur = conn.execute(
            "INSERT INTO reservations (store_id, source, external_id, kind, at, people, name, memo, status, created_at, updated_at) "
            "VALUES (?, 'OWNER', NULL, ?, ?, ?, ?, ?, 'CONFIRMED', ?, ?)",
            (store_id, kind, to_seoul(at).isoformat(), people, name.strip(), memo.strip(), now, now),
        )
        new_id = cur.lastrowid
    return get(new_id)


def get(reservation_id: int) -> dict | None:
    with _db() as conn:
        found = conn.execute(f"SELECT {', '.join(COLUMNS)} FROM reservations WHERE reservation_id = ?", (reservation_id,)).fetchone()
    return _row(found) if found else None


def set_status(reservation_id: int, status: str) -> dict:
    """예약 문의를 받거나(CONFIRMED) 어렵다고 답하거나(DECLINED), 사장님이 적은 예약을 지운다(CANCELED).
    네이버 예약은 진짜로는 네이버에 답을 보내야 한다 (지금은 목업이라 여기 기록만 바꾼다)."""
    if status not in STATUSES:
        raise ReservationError("BAD_STATUS", "다시 눌러 주세요")
    row = get(reservation_id)
    if row is None:
        raise ReservationError("NOT_FOUND", "예약을 찾지 못했어요")
    if row["status"] != status and ((row["status"], status) not in CHANGES or (status == "CANCELED" and row["source"] != "OWNER")):
        raise ReservationError("BAD_TRANSITION", "이미 정한 예약이에요")
    if row["status"] == status:
        return row  # 같은 상태로 다시 누름: 그대로 성공
    # 읽은 상태일 때만 바꾼다 (with 는 커밋만 하고 cur.rowcount 는 그대로 남는다)
    with _db() as conn:
        cur = conn.execute(
            "UPDATE reservations SET status = ?, updated_at = ? WHERE reservation_id = ? AND status = ?",
            (status, now_seoul().isoformat(), reservation_id, row["status"]),
        )
    if cur.rowcount == 0:  # 그 사이 다른 요청이 먼저 바꿨다
        raise ReservationError("BAD_TRANSITION", "이미 정한 예약이에요")
    return get(reservation_id)
