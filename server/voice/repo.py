"""음성 백엔드 저장소 (sqlite, db/app_data/voice.db).

종류(kind)마다 문서 8장 모양의 JSON 을 한 줄씩 둔다. 목업 단계라 표를 잘게 나누지 않았다.
  store        가게 (menus, facts, open_time, close_time, closed_weekdays, location 포함)
  review       리뷰 + 덧붙인 칸 (sentiment, topic, summary, reply_*)
  reservation  예약 (kind 는 party_size 로 정한다)
  event, game  행사, 경기
  weather      날씨 (id = 가게:날짜)
  settings     허락 설정 (id = 가게)
  job          작업 큐
  briefing     미리 만든 브리핑 묶음 (id = 가게:날짜)
  session      브리핑 진행 상태 (id = session_id)
  turn         request_id → 응답 (같은 요청이 다시 오면 같은 응답)
"""

import json
import sqlite3
import threading
from pathlib import Path

from voice import config

_lock = threading.RLock()


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
    return conn


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


# ── 자주 쓰는 모양 ──


def store(store_id: str) -> dict | None:
    return get("store", store_id)


def reviews(store_id: str) -> list[dict]:
    return all_of("review", store_id)


def review(review_id: str) -> dict | None:
    return get("review", review_id)


def save_review(data: dict) -> dict:
    return put("review", data["id"], data["store_id"], data)


def settings(store_id: str) -> dict:
    return get("settings", store_id) or {"negative_review_auto_reply": None}


def save_settings(store_id: str, data: dict) -> dict:
    return put("settings", store_id, store_id, data)
