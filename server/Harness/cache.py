"""에이전트 결과 캐시. 키는 (에이전트, 가게, 입력 해시, 프롬프트 버전).

에이전트가 스스로 만든 제안(source == "AGENT")만 기억한다. 물러나기 결과는 기억하지 않아 다음 계산 때 다시 시도한다.

두 층으로 기억한다 (2026-11-18).
  1. 서버 메모리: 가장 빠르다. 서버를 다시 켜면 비워진다
  2. 파일 (CACHE_PATH, server/db/app_data/harness_cache.db, git 에 올리지 않는다): 서버를 다시 켜도 남는다.
     같은 리뷰·같은 프롬프트면 CLOVA 를 다시 부르지 않는다. 음성 서버의 "처음부터"(브리핑을 다시 준비)가
     두 번째부터는 몇 초 안에 끝난다. 프롬프트나 도구 모양을 고치면 키(프롬프트 해시)가 달라져 저절로 새로 부른다.
JSON 으로 바꿀 수 있는 값(Proposal, 글자, 목록 …)만 파일에 둔다. 그 밖의 값은 메모리에만 둔다.

clear() 는 메모리만 비운다 (측정 도구가 "이번에는 새로 불러 봐"할 때). 파일까지 지우려면 clear_disk().
시험은 CACHE_PATH 를 None 으로 두어 파일 층을 끈다 (Harness/tests, voice/tests, tests 의 conftest). 파일 층 시험만 임시 파일을 쓴다.
"""

import dataclasses
import hashlib
import json
import logging
import sqlite3
import threading
from pathlib import Path

logger = logging.getLogger(__name__)

CACHE_PATH: Path | None = Path(__file__).resolve().parents[1] / "db" / "app_data" / "harness_cache.db"  # None 이면 메모리만

_results: dict[tuple[str, str, str, str], object] = {}
_guard = threading.Lock()


def digest(value: object) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


# ── 파일 ──


def _db() -> sqlite3.Connection:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(CACHE_PATH)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS results (agent TEXT NOT NULL, store_id TEXT NOT NULL, input_hash TEXT NOT NULL,"
        " prompt_hash TEXT NOT NULL, value TEXT NOT NULL, saved_at TEXT NOT NULL DEFAULT (datetime('now')),"
        " PRIMARY KEY (agent, store_id, input_hash, prompt_hash))"
    )
    return conn


PROPOSAL_TAG = "__proposal__"
_PROPOSAL_KEYS = {"agent", "task_id", "content", "source", "run_id"}


def _encode(value: object) -> object:
    """Proposal 을 안쪽까지 표시를 달아 바꾼다. asdict 는 안쪽 Proposal 을 표시 없는 dict 로 만들어 되살리지 못했다 (H1).
    새 dict·list 를 만들어 원본은 고치지 않는다."""
    from Harness.spec import Proposal

    if isinstance(value, Proposal):
        return {PROPOSAL_TAG: {f.name: _encode(getattr(value, f.name)) for f in dataclasses.fields(value)}}
    if isinstance(value, dict):
        return {key: _encode(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_encode(item) for item in value]
    return value


def _decode_hook(data: dict) -> object:
    from Harness.spec import Proposal

    if set(data) == {PROPOSAL_TAG}:
        return Proposal(**data[PROPOSAL_TAG])
    return data


def _has_bare_proposal(value: object) -> bool:
    """예전 모양(asdict)에서 Proposal 이었다가 표시 없는 dict 가 된 것이 안에 있는지."""
    if isinstance(value, dict):
        return _PROPOSAL_KEYS <= set(value) or any(_has_bare_proposal(item) for item in value.values())
    if isinstance(value, list):
        return any(_has_bare_proposal(item) for item in value)
    return False


def _dump(value: object) -> str | None:
    try:
        return json.dumps({"type": "tagged", "value": _encode(value)}, ensure_ascii=False)
    except (TypeError, ValueError):
        return None  # JSON 으로 못 바꾸는 값은 메모리에만


def _load(text: str) -> object | None:
    from Harness.spec import Proposal

    data = json.loads(text, object_hook=_decode_hook)
    if data.get("type") == "tagged":
        return data.get("value")
    if data.get("type") == "proposal":  # 예전 모양 (파일에 이미 쌓여 있다)
        fields = data["fields"]
        if _has_bare_proposal(fields.get("content")):
            return None  # 안쪽 Proposal 을 되살릴 수 없어 빗나감으로 본다. 다시 부르면 새 모양으로 저장된다
        return Proposal(**fields)
    return data.get("value")


def _disk_get(key: tuple[str, str, str, str]) -> object | None:
    if CACHE_PATH is None:
        return None
    try:
        with _db() as conn:
            row = conn.execute(
                "SELECT value FROM results WHERE agent = ? AND store_id = ? AND input_hash = ? AND prompt_hash = ?", key
            ).fetchone()
        return _load(row[0]) if row else None
    except (sqlite3.Error, ValueError, TypeError, KeyError):
        logger.exception("캐시 파일을 읽지 못했어요")
        return None


def _disk_put(key: tuple[str, str, str, str], value: object) -> None:
    text = _dump(value) if CACHE_PATH is not None else None
    if text is None:
        return
    try:
        with _db() as conn:
            conn.execute("INSERT OR REPLACE INTO results (agent, store_id, input_hash, prompt_hash, value) VALUES (?, ?, ?, ?, ?)",
                         (*key, text))
    except sqlite3.Error:
        logger.exception("캐시 파일에 쓰지 못했어요")


# ── 쓰는 곳 ──


def get(key: tuple[str, str, str, str]) -> object | None:
    with _guard:
        if key in _results:
            return _results[key]
        found = _disk_get(key)
        if found is not None:
            _results[key] = found
        return found


def put(key: tuple[str, str, str, str], value: object) -> None:
    with _guard:
        _results[key] = value
        _disk_put(key, value)


def clear() -> None:
    """메모리만 비운다. 파일에 둔 결과는 남는다."""
    with _guard:
        _results.clear()


def clear_disk() -> None:
    """파일에 둔 결과까지 모두 지운다 (프롬프트가 아닌 다른 이유로 다시 받아야 할 때)."""
    with _guard:
        _results.clear()
        if CACHE_PATH is None:
            return
        try:
            with _db() as conn:
                conn.execute("DELETE FROM results")
        except sqlite3.Error:
            logger.exception("캐시 파일을 비우지 못했어요")
