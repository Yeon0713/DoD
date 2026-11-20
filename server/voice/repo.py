"""음성 백엔드 저장소 (sqlite, db/app_data/voice.db).

종류(kind)마다 문서 8장 모양의 JSON 을 한 줄씩 둔다. 목업 단계라 표를 잘게 나누지 않았다.
  store        가게 (menus, facts, open_time, close_time, closed_weekdays, location 포함.
               사장님이 요일마다 고치면 weekly_hours, 그 전 네이버 시간은 naver_hours. voice/hours.py)
  review       리뷰 + 덧붙인 칸 (sentiment, topic, summary, reply_*)
  reservation  예약 (kind 는 party_size 로 정한다)
  event, game  행사, 경기
  weather      날씨 (id = 가게:날짜)
  settings     허락 설정, 브리핑 알림 (id = 가게)
  sales        포스 매출 (id = 가게, 매출 탭)
  revisit      도나 답글을 받고 다시 온 손님 (매출 탭 G-04 ③)
  job          작업 큐
  briefing     미리 만든 브리핑 묶음 (id = 가게:날짜)
  session      브리핑 진행 상태 (id = session_id)
  turn         request_id → 응답 (같은 요청이 다시 오면 같은 응답)

알바생은 사람마다 아이디·비밀번호·할 일·한 일을 꺼내 봐야 해서 JSON 서랍이 아니라 표를 따로 둔다 (STAFF_TABLES).
읽고 쓰는 곳은 voice/staff_db.py 하나다. 가게를 지우거나(delete_store) 처음부터 할 때(reset) 같이 지운다.
"""

import json
import sqlite3
import threading
from pathlib import Path

from voice import config

_lock = threading.RLock()

# 알바생 표 (voice/staff_db.py). 시각은 모두 ISO 글자(+09:00), 날짜는 "2026-11-17".
STAFF_TABLES = {
    # 알바생 한 명. status: listed(명단만) | invited(초대 코드를 받음) | joined(가입함) | removed(사장님이 내보냄)
    "staff_members": """
        staff_id TEXT PRIMARY KEY, store_id TEXT NOT NULL, name TEXT NOT NULL, call TEXT NOT NULL,
        login_id TEXT UNIQUE, password_hash TEXT, status TEXT NOT NULL,
        signed_up_at TEXT, started_at TEXT, removed_at TEXT, created_at TEXT NOT NULL""",
    # 초대 코드 한 개 (한 사람용). shared_at: 사장님이 카카오톡으로 보냄, used_at: 그 코드로 가입함
    "staff_invites": """
        code TEXT PRIMARY KEY, store_id TEXT NOT NULL, staff_id TEXT NOT NULL,
        created_at TEXT NOT NULL, shared_at TEXT, used_at TEXT, revoked_at TEXT""",
    # 할 일 하나. repeat: daily(매뉴얼) | today(오늘만), kind: do(할 것) | dont(하지 말 것),
    # to_staff: all(오늘 나온 사람 모두) | everyone(알바생 모두) | 알바생 번호, origin: manual | owner(사장님 말) | review(교정 카드) | story_event(이벤트 카드) | field_variable(날씨·예약)
    "staff_tasks": """
        task_id TEXT PRIMARY KEY, store_id TEXT NOT NULL, title TEXT NOT NULL, phase TEXT NOT NULL,
        repeat TEXT NOT NULL, kind TEXT NOT NULL, must_confirm INTEGER NOT NULL, urgent INTEGER NOT NULL,
        to_staff TEXT NOT NULL, origin TEXT NOT NULL, detail TEXT, owner_words TEXT, source TEXT,
        start_date TEXT NOT NULL, end_date TEXT NOT NULL, sent_at TEXT, canceled_at TEXT, created_at TEXT NOT NULL""",
    # 누가 어느 날 그 일을 했는지(done_at), 확인했는지(confirmed_at)
    "staff_task_marks": """
        task_id TEXT NOT NULL, staff_id TEXT NOT NULL, day TEXT NOT NULL, store_id TEXT NOT NULL,
        done_at TEXT, confirmed_at TEXT, PRIMARY KEY (task_id, staff_id, day)""",
    # 출퇴근: 그날 할 일 화면을 처음 연 시각이 출근, 퇴근하기를 누른 시각이 퇴근
    "staff_attendance": """
        staff_id TEXT NOT NULL, day TEXT NOT NULL, store_id TEXT NOT NULL, in_at TEXT NOT NULL, out_at TEXT,
        PRIMARY KEY (staff_id, day)""",
    # 로그인 표시(토큰). 알바생 화면이 요청마다 보내고, 서버는 이것으로 누구인지 안다
    "staff_sessions": """
        token TEXT PRIMARY KEY, staff_id TEXT NOT NULL, store_id TEXT NOT NULL, created_at TEXT NOT NULL""",
}


def _path() -> Path:
    return config.DB_PATH


def _db() -> sqlite3.Connection:
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS docs (kind TEXT NOT NULL, id TEXT NOT NULL, store_id TEXT, data TEXT NOT NULL,"
        " PRIMARY KEY (kind, id))"
    )
    conn.execute("CREATE TABLE IF NOT EXISTS counters (name TEXT PRIMARY KEY, value INTEGER NOT NULL)")
    for table, columns in STAFF_TABLES.items():
        conn.execute(f"CREATE TABLE IF NOT EXISTS {table} ({columns})")
    return conn


def connect() -> sqlite3.Connection:
    """알바생 표를 읽고 쓸 연결 (voice/staff_db.py). 줄을 이름으로 꺼낼 수 있게 한다. 쓸 때는 lock() 안에서."""
    conn = _db()
    conn.row_factory = sqlite3.Row
    return conn


def lock() -> threading.RLock:
    return _lock


def put(kind: str, doc_id: str, store_id: str | None, data: dict) -> dict:
    with _lock, _db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO docs (kind, id, store_id, data) VALUES (?, ?, ?, ?)",
            (kind, doc_id, store_id, json.dumps(data, ensure_ascii=False)),
        )
    return data


def get(kind: str, doc_id: str) -> dict | None:
    with _lock, _db() as conn:
        row = conn.execute("SELECT data FROM docs WHERE kind = ? AND id = ?", (kind, doc_id)).fetchone()
    return json.loads(row[0]) if row else None


def all_of(kind: str, store_id: str) -> list[dict]:
    with _lock, _db() as conn:
        rows = conn.execute("SELECT data FROM docs WHERE kind = ? AND store_id = ? ORDER BY rowid", (kind, store_id)).fetchall()
    return [json.loads(row[0]) for row in rows]


def store_ids() -> list[str]:
    with _lock, _db() as conn:
        return [row[0] for row in conn.execute("SELECT id FROM docs WHERE kind = 'store' ORDER BY rowid").fetchall()]


def kinds_of(store_id: str) -> dict[str, list[dict]]:
    with _lock, _db() as conn:
        rows = conn.execute("SELECT kind, data FROM docs WHERE store_id = ? ORDER BY rowid", (store_id,)).fetchall()
    result: dict[str, list[dict]] = {}
    for kind, data in rows:
        result.setdefault(kind, []).append(json.loads(data))
    return result


def delete_store(store_id: str) -> None:
    with _lock, _db() as conn:
        conn.execute("DELETE FROM docs WHERE store_id = ?", (store_id,))
        for table in STAFF_TABLES:
            conn.execute(f"DELETE FROM {table} WHERE store_id = ?", (store_id,))


def store_docs(store_id: str) -> list[dict]:
    """한 가게의 모든 문서 {kind, id, data} (넣은 순서대로). 밤사이 준비 결과를 저장할 때 (voice/prepared_snapshot.py)."""
    with _lock, _db() as conn:
        rows = conn.execute("SELECT kind, id, data FROM docs WHERE store_id = ? ORDER BY rowid", (store_id,)).fetchall()
    return [{"kind": kind, "id": doc_id, "data": json.loads(data)} for kind, doc_id, data in rows]


def put_many(store_id: str, docs: list[dict]) -> None:
    with _lock, _db() as conn:
        conn.executemany("INSERT OR REPLACE INTO docs (kind, id, store_id, data) VALUES (?, ?, ?, ?)",
                         [(d["kind"], d["id"], store_id, json.dumps(d["data"], ensure_ascii=False)) for d in docs])


def counters_of(store_id: str) -> dict[str, int]:
    """번호표 중 이 가게 것 (이름이 '...:가게' 로 끝난다. 예: review:s005)."""
    with _lock, _db() as conn:
        rows = conn.execute("SELECT name, value FROM counters WHERE name LIKE ?", (f"%:{store_id}",)).fetchall()
    return dict(rows)


def set_counters(values: dict[str, int]) -> None:
    with _lock, _db() as conn:
        conn.executemany("INSERT OR REPLACE INTO counters (name, value) VALUES (?, ?)", list(values.items()))


def next_number(name: str) -> int:
    """이름마다 1 부터 올라가는 번호 (리뷰 id, turn id 등)."""
    with _lock, _db() as conn:
        row = conn.execute("SELECT value FROM counters WHERE name = ?", (name,)).fetchone()
        value = (row[0] if row else 0) + 1
        conn.execute("INSERT OR REPLACE INTO counters (name, value) VALUES (?, ?)", (name, value))
    return value


def reset() -> None:
    with _lock, _db() as conn:
        conn.execute("DELETE FROM docs")
        conn.execute("DELETE FROM counters")
        for table in STAFF_TABLES:
            conn.execute(f"DELETE FROM {table}")


# ── 자주 쓰는 모양 ──


def store(store_id: str) -> dict | None:
    return get("store", store_id)


def reviews(store_id: str) -> list[dict]:
    return all_of("review", store_id)


def review(review_id: str) -> dict | None:
    return get("review", review_id)


def save_review(data: dict) -> dict:
    return put("review", data["id"], data["store_id"], data)


def save_review_if(data: dict, reply_status: str) -> dict | None:
    """저장된 리뷰의 답글 상태가 아직 reply_status 일 때만 저장한다. 아니면 저장하지 않고 None.
    오래 걸리는 일(답글 쓰기, LLM)이 리뷰를 읽은 뒤 다른 작업(아쉬운 리뷰 알림, 사장님 대답)이 상태를 바꿨으면 덮지 않는다."""
    with _lock:
        current = get("review", data["id"])
        if current is not None and current.get("reply_status", "none") != reply_status:
            return None
        return save_review(data)


def settings(store_id: str) -> dict:
    return get("settings", store_id) or {}


def save_settings(store_id: str, data: dict) -> dict:
    return put("settings", store_id, store_id, data)
