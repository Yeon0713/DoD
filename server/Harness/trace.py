"""에이전트 실행 기록. 실행(run) 하나에 단계마다 한 줄씩 남긴다.

설계 문서는 기존 clova_usage_log 에 run_id 칸을 더하자고 했지만, 기존 코드를 고치지 않기로 해서 따로 둔다.
CLOVA 호출 자체(토큰, 비용, 통과/버림)는 기존 clova_usage_log.record_call 로도 남겨 개발자 대시보드 'AI 비용'에 보인다.

저장 위치: server/db/app_data/harness_trace.db (db/app_data 는 git 에 올라가지 않는다)
kind: start(시작, name = 맡은 일 id), llm(CLOVA 호출), tool(조회 도구), submit(제출과 판정), fallback(물러나기),
      cache(캐시에서 꺼냄), end(끝)
기존 서버와 음성 백엔드(server/voice)가 같은 파일에 쓴다. 개발자 대시보드 '에이전트' 탭이 recent_runs 로 둘 다 읽는다.
"""

import datetime as dt
import json
import logging
import sqlite3
import threading
import uuid
from contextlib import closing
from pathlib import Path

from app.core.seoul_time import now_seoul

TRACE_PATH = Path(__file__).resolve().parents[1] / "db" / "app_data" / "harness_trace.db"
DETAIL_LENGTH = 500
LOCK_WAIT_SECONDS = 10  # 다른 서버(기존 서버·음성 서버·평가)가 같은 파일에 쓰는 중이면 기다리는 시간

logger = logging.getLogger(__name__)
_write_lock = threading.Lock()  # 한 프로세스 안의 스레드만 줄 세운다. 다른 프로세스와는 SQLite 파일 잠금으로 나눈다
_wal_paths: set[Path] = set()


def new_run_id() -> str:
    return uuid.uuid4().hex[:12]


def _db() -> sqlite3.Connection:
    TRACE_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(TRACE_PATH, timeout=LOCK_WAIT_SECONDS)
    conn.row_factory = sqlite3.Row
    if TRACE_PATH not in _wal_paths:  # 파일에 남으므로 한 번이면 된다. 읽기(대시보드)와 쓰기가 서로 막지 않는다 (H5)
        conn.execute("PRAGMA journal_mode=WAL")
        _wal_paths.add(TRACE_PATH)
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
    name: str | None = None, detail: object = None, limit: int | None = DETAIL_LENGTH,
) -> None:
    """limit: detail 을 자르는 길이. None 이면 자르지 않는다: 평가가 근거를 다시 세는 줄(입력, 도구 결과)은 runner 가 None 을 준다 (H6, H10)."""
    text = detail if isinstance(detail, str) or detail is None else json.dumps(detail, ensure_ascii=False, default=str)
    if text is not None and limit is not None and len(text) > limit:
        text = text[:limit] + "…"
    try:  # 기록은 대시보드용 부가 기능이다. 잠금·디스크 오류로 실패해도 에이전트 실행은 계속한다 (H5)
        with _write_lock, closing(_db()) as conn, conn:
            conn.execute(
                "INSERT INTO steps (at, run_id, parent_run_id, agent, store_id, step, kind, name, detail)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (now_seoul().isoformat(timespec="seconds"), run_id, parent_run_id, agent, store_id, step, kind, name, text),
            )
    except Exception:
        logger.exception("실행 기록 실패: %s %s %s", agent, run_id, kind)


def steps_of(run_id: str) -> list[dict]:
    """실행 하나의 단계들. 그 실행 아래(parent_run_id 가 이 실행인) 일꾼 실행의 단계도 함께, 기록 순서대로."""
    with closing(_db()) as conn:
        rows = conn.execute(
            "SELECT * FROM steps WHERE run_id = ? OR parent_run_id = ? ORDER BY id", (run_id, run_id)
        ).fetchall()
    return [dict(row) for row in rows]


RUNNING_WINDOW_SECONDS = 300  # 끝난 줄 없이 이보다 오래 조용한 실행은 '멈춤'으로 본다 (서버가 꺼졌거나 오류)


def _outcome(rows: list[dict]) -> str:
    """실행 하나의 결과: accepted(에이전트 통과) | cache | fallback(기존 단일 호출로 물러남) | failed | running."""
    for row in reversed(rows):
        if row["kind"] == "cache":
            return "cache"
        if row["kind"] == "end" and row["name"] == "accepted":
            return "accepted"
        if row["kind"] == "fallback":
            return "fallback" if row["name"] == "ok" else "failed"
    return "running"


def recent_runs(limit: int = 100, scan_rows: int = 5000) -> list[dict]:
    """최근 실행들 (최근 것 먼저). 실행마다 에이전트, 가게, 맡은 일, 시작·마지막 시각, CLOVA 호출 수, 결과."""
    with closing(_db()) as conn:
        rows = [dict(r) for r in conn.execute("SELECT * FROM steps ORDER BY id DESC LIMIT ?", (scan_rows,)).fetchall()]
    by_run: dict[str, list[dict]] = {}
    for row in reversed(rows):
        by_run.setdefault(row["run_id"], []).append(row)
    now_shifted, now_real = now_seoul(), dt.datetime.now(now_seoul().tzinfo)
    runs = []
    for run_id, steps in by_run.items():
        start = next((s for s in steps if s["kind"] == "start"), steps[0])
        outcome = _outcome(steps)
        last_at = dt.datetime.fromisoformat(steps[-1]["at"])
        if outcome == "running" and min(abs((now_shifted - last_at).total_seconds()), abs((now_real - last_at).total_seconds())) > RUNNING_WINDOW_SECONDS:
            outcome = "stalled"
        rejected = sum(1 for s in steps if s["kind"] == "submit" and '"accepted": false' in (s["detail"] or ""))
        runs.append({
            "run_id": run_id, "parent_run_id": start["parent_run_id"], "agent": start["agent"], "store_id": start["store_id"],
            "task": start["name"] if start["kind"] == "start" else None, "started_at": steps[0]["at"], "last_at": steps[-1]["at"],
            "llm_calls": sum(1 for s in steps if s["kind"] == "llm"), "tools": sum(1 for s in steps if s["kind"] == "tool"),
            "rejections": rejected, "outcome": outcome, "last_step": f"{steps[-1]['kind']} {steps[-1]['name'] or ''}".strip(),
        })
    runs.sort(key=lambda r: r["last_at"], reverse=True)
    return runs[:limit]
