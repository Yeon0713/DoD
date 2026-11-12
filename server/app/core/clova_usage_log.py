"""CLOVA X 호출 기록. 개발자 대시보드(dev/)의 'AI 비용', 'AI 품질' 탭이 읽는다.

CLOVA 를 부를 때마다(app/core/clova.py 의 ask) 한 줄씩 남긴다.
- 언제, 어느 기능(답글 초안, 문장 다듬기 …), 어느 가게, 입력·출력 토큰 수, 걸린 시간, 성공했는지
- 부른 쪽이 답을 검사한 뒤 통과/버림과 버린 이유를 붙인다 (set_verdict)
- 보낸 글과 받은 답은 앞부분 200자만 남긴다. 리뷰 글은 부르는 쪽에서 전화번호·닉네임을 가린 뒤라 그대로 둔다

저장 위치: server/db/app_data/clova_usage.db (git 에 올라가지 않는다. 지우면 기록이 처음부터 다시 쌓인다)
비용(원) = 토큰 수 × .env 의 CLOVA_PRICE_INPUT_PER_1K / CLOVA_PRICE_OUTPUT_PER_1K ÷ 1000
"""

import datetime as dt
import sqlite3
import threading
from pathlib import Path

from app.core.config import settings
from app.core.seoul_time import now_seoul

LOG_PATH = Path(__file__).resolve().parents[2] / "db" / "app_data" / "clova_usage.db"
EXCERPT_LENGTH = 200

FEATURE_NAMES = {
    "reply_draft": "리뷰 답글 초안",
    "reorder_nudge": "재주문 인사",
    "reply_rewrite": "답글 다시 쓰기",
    "polish:calendar_reason": "달력 이유 다듬기",
    "polish:plan_card": "카드 문구 다듬기",
    "polish:notice": "알림 글 다듬기",
    "other": "기타",
}

_local = threading.local()  # 이 스레드가 마지막으로 남긴 기록 id (set_verdict 가 쓴다)
_write_lock = threading.Lock()


def _db() -> sqlite3.Connection:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(LOG_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS calls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            at TEXT NOT NULL,              -- 서울 시각 ISO
            feature TEXT NOT NULL,
            store_id TEXT,
            model TEXT NOT NULL,
            input_tokens INTEGER,          -- CLOVA 응답의 usage. 없으면 NULL
            output_tokens INTEGER,
            latency_ms INTEGER NOT NULL,
            status TEXT NOT NULL,          -- ok, http_error, connection_error
            http_status INTEGER,
            verdict TEXT,                  -- accepted, rejected. 검사하지 않았으면 NULL
            reason TEXT,                   -- 버린 이유
            request_excerpt TEXT,
            answer_excerpt TEXT
        )
        """
    )
    return conn


def _excerpt(text: str | None) -> str | None:
    if text is None:
        return None
    text = " ".join(text.split())
    return text if len(text) <= EXCERPT_LENGTH else text[:EXCERPT_LENGTH] + "…"


def record_call(
    *,
    feature: str,
    store_id: str | None,
    input_tokens: int | None,
    output_tokens: int | None,
    latency_ms: int,
    status: str,
    http_status: int | None,
    request_text: str,
    answer_text: str | None,
) -> int:
    """호출 한 번을 남기고 id 를 돌려준다. 같은 스레드의 다음 set_verdict 가 이 기록에 붙는다."""
    with _write_lock, _db() as conn:
        cursor = conn.execute(
            "INSERT INTO calls (at, feature, store_id, model, input_tokens, output_tokens, latency_ms, status,"
            " http_status, request_excerpt, answer_excerpt) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                now_seoul().isoformat(timespec="seconds"),
                feature,
                store_id,
                settings.clova_studio_model,
                input_tokens,
                output_tokens,
                latency_ms,
                status,
                http_status,
                _excerpt(request_text),
                _excerpt(answer_text),
            ),
        )
        _local.last_id = cursor.lastrowid
        return cursor.lastrowid


def set_verdict(accepted: bool, reason: str | None = None) -> None:
    """이 스레드가 마지막으로 부른 CLOVA 답을 검사한 결과를 붙인다. 부른 기록이 없으면 아무 일도 하지 않는다."""
    call_id = getattr(_local, "last_id", None)
    if call_id is None:
        return
    with _write_lock, _db() as conn:
        conn.execute(
            "UPDATE calls SET verdict = ?, reason = ? WHERE id = ?",
            ("accepted" if accepted else "rejected", None if accepted else reason, call_id),
        )
    _local.last_id = None


# ── 읽기 (대시보드용) ──


def cost_won(input_tokens: int, output_tokens: int) -> float:
    return (
        input_tokens * settings.clova_price_input_per_1k + output_tokens * settings.clova_price_output_per_1k
    ) / 1000


def _since(days: int) -> str:
    return (now_seoul() - dt.timedelta(days=days)).isoformat(timespec="seconds")


def _total_row(row: sqlite3.Row) -> dict:
    input_tokens, output_tokens = row["input_tokens"] or 0, row["output_tokens"] or 0
    return {
        "calls": row["calls"],
        "failed": row["failed"] or 0,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_won": round(cost_won(input_tokens, output_tokens), 2),
    }


TOTALS = (
    "COUNT(*) AS calls, SUM(status != 'ok') AS failed, "
    "SUM(COALESCE(input_tokens, 0)) AS input_tokens, SUM(COALESCE(output_tokens, 0)) AS output_tokens"
)


def usage_summary(days: int) -> dict:
    """지난 days 일 동안의 합계와 기능별·가게별·날짜별 나눔."""
    since = _since(days)
    with _db() as conn:
        total = conn.execute(f"SELECT {TOTALS} FROM calls WHERE at >= ?", (since,)).fetchone()
        by_feature = conn.execute(
            f"SELECT feature, {TOTALS} FROM calls WHERE at >= ? GROUP BY feature ORDER BY calls DESC", (since,)
        ).fetchall()
        by_store = conn.execute(
            f"SELECT COALESCE(store_id, '-') AS store_id, {TOTALS} FROM calls WHERE at >= ?"
            " GROUP BY store_id ORDER BY calls DESC",
            (since,),
        ).fetchall()
        by_day = conn.execute(
            f"SELECT substr(at, 1, 10) AS day, {TOTALS} FROM calls WHERE at >= ? GROUP BY day ORDER BY day", (since,)
        ).fetchall()
        no_usage = conn.execute(
            "SELECT COUNT(*) FROM calls WHERE at >= ? AND status = 'ok' AND input_tokens IS NULL", (since,)
        ).fetchone()[0]
    return {
        "total": _total_row(total),
        "by_feature": [{"feature": r["feature"], "name": FEATURE_NAMES.get(r["feature"], r["feature"]), **_total_row(r)} for r in by_feature],
        "by_store": [{"store_id": r["store_id"], **_total_row(r)} for r in by_store],
        "by_day": [{"day": r["day"], **_total_row(r)} for r in by_day],
        "calls_without_token_info": no_usage,
    }


def quality_summary(limit: int) -> dict:
    """기능별 통과·버림·실패 수, 버린 이유 순위, 최근 호출 목록."""
    with _db() as conn:
        by_feature = conn.execute(
            "SELECT feature, COUNT(*) AS calls, SUM(verdict = 'accepted') AS accepted, SUM(verdict = 'rejected') AS rejected,"
            " SUM(status != 'ok') AS failed, AVG(latency_ms) AS avg_latency_ms FROM calls GROUP BY feature ORDER BY calls DESC"
        ).fetchall()
        reasons = conn.execute(
            "SELECT reason, COUNT(*) AS count FROM calls WHERE verdict = 'rejected' GROUP BY reason ORDER BY count DESC LIMIT 10"
        ).fetchall()
        recent = conn.execute("SELECT * FROM calls ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return {
        "by_feature": [
            {
                "feature": r["feature"],
                "name": FEATURE_NAMES.get(r["feature"], r["feature"]),
                "calls": r["calls"],
                "accepted": r["accepted"] or 0,
                "rejected": r["rejected"] or 0,
                "failed": r["failed"] or 0,
                "avg_latency_ms": round(r["avg_latency_ms"] or 0),
            }
            for r in by_feature
        ],
        "reject_reasons": [{"reason": r["reason"] or "(이유 없음)", "count": r["count"]} for r in reasons],
        "recent": [{**dict(r), "feature_name": FEATURE_NAMES.get(r["feature"], r["feature"])} for r in recent],
    }


def clear() -> None:
    """기록을 모두 지운다 (대시보드 조작 탭, 테스트용)."""
    with _write_lock:
        LOG_PATH.unlink(missing_ok=True)
