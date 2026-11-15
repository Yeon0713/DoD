"""에이전트 실행 기록. 실행(run) 하나에 단계마다 한 줄씩 남긴다.

설계 문서는 기존 clova_usage_log 에 run_id 칸을 더하자고 했지만, 기존 코드를 고치지 않기로 해서 따로 둔다.
CLOVA 호출 자체(토큰, 비용, 통과/버림)는 기존 clova_usage_log.record_call 로도 남겨 개발자 대시보드 'AI 비용'에 보인다.

저장 위치: server/db/app_data/harness_trace.db (db/app_data 는 git 에 올라가지 않는다)
kind: llm(CLOVA 호출), tool(조회 도구), submit(제출과 판정), fallback(물러나기), cache(캐시에서 꺼냄), end(끝)
"""

import json
import sqlite3
import threading
import uuid
from pathlib import Path

from app.core.seoul_time import now_seoul

TRACE_PATH = Path(__file__).resolve().parents[1] / "db" / "app_data" / "harness_trace.db"
DETAIL_LENGTH = 500

_write_lock = threading.Lock()


def new_run_id() -> str:
    return uuid.uuid4().hex[:12]


def _db() -> sqlite3.Connection:
    TRACE_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(TRACE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS steps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            at TEXT NOT NULL,
            run_id TEXT NOT NULL,
            parent_run_id TEXT,
            agent TEXT NOT NULL,
            store_id TEXT,
            step INTEGER NOT NULL,
            kind TEXT NOT NULL,
            name TEXT,
            detail TEXT
        )
        """
    )
    return conn


def record(
    *, run_id: str, parent_run_id: str | None, agent: str, store_id: str | None, step: int, kind: str,
    name: str | None = None, detail: object = None,
) -> None:
    text = detail if isinstance(detail, str) or detail is None else json.dumps(detail, ensure_ascii=False, default=str)
    if text is not None and len(text) > DETAIL_LENGTH:
        text = text[:DETAIL_LENGTH] + "…"
    with _write_lock, _db() as conn:
        conn.execute(
            "INSERT INTO steps (at, run_id, parent_run_id, agent, store_id, step, kind, name, detail)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (now_seoul().isoformat(timespec="seconds"), run_id, parent_run_id, agent, store_id, step, kind, name, text),
        )


def steps_of(run_id: str) -> list[dict]:
    """실행 하나의 단계들. 그 실행 아래(parent_run_id 가 이 실행인) 일꾼 실행의 단계도 함께, 기록 순서대로."""
    with _db() as conn:
        rows = conn.execute(
            "SELECT * FROM steps WHERE run_id = ? OR parent_run_id = ? ORDER BY id", (run_id, run_id)
        ).fetchall()
    return [dict(row) for row in rows]
