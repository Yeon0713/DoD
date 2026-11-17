"""평가 사례 하나가 왜 에이전트 답(AGENT)으로 끝나지 못했는지와, 제출이 몇 번 거절됐는지를 실행 기록에서 읽는다.

하네스 코드는 바꾸지 않는다. runner 가 trace 에 남기는 단계만 본다:
  end      accepted | time_budget | call_budget | too_many_rejections
  llm      failed (CLOVA 호출이 None 으로 끝남. 까닭은 trace 에 없다)
  submit   detail {"accepted": bool, "reason": str}
llm failed 의 까닭은 사례를 도는 동안 post 를 감싸 모은 전송 사건(transport events)으로 가른다:
  429·5xx 응답, 연결 실패, 시간 초과 → transport / 그 밖의 4xx(요청 모양 오류 등) → other

fail_cause (사례마다 하나)
  none       답이 에이전트(AGENT) 또는 단일 호출 성공(SINGLE_CALL, 기준선 S)
  transport  전송 실패가 있었고 호출 실패로 끝남
  rejected   검사 거절이 상한에 닿음 (too_many_rejections). S 는 두 번 모두 검사(rejection_reason)에 걸림
  budget     시간·호출·단계 상한에 닿음 (time_budget, call_budget, 단계 상한)
  no_submit  제출 없이 끝남 (글로만 답함, 길이 초과 등)
  other      위에 없음. fail_detail 에 까닭 글
fail_cause 는 생성이 왜 실패했는지만 말한다. 적합(심판·코드 검사)과 검사 통과/거절 비율은 따로 센다.

제출 통계 (사례 = 논리 작업 하나)
  submits      제출 수 (A·B: trace submit 단계, B 는 아래 일꾼 실행 포함 / S: 답이 온 시도)
  first_ok     첫 제출이 검사를 통과했나 (제출이 없으면 None)
  rejections   거절된 제출 수
  recovered_at 첫 제출이 거절된 뒤 통과했으면 그때까지 거절 수 (1 = 한 번 거절 뒤 통과). 아니면 None
"""

import json
import sqlite3
from collections.abc import Iterable
from pathlib import Path

CAUSES = ("none", "transport", "rejected", "budget", "no_submit", "other")
SUCCESS_SOURCES = ("AGENT", "SINGLE_CALL")
BUDGET_ENDS = ("time_budget", "call_budget")


# ── 전송 사건 ──


def is_transport(event: object) -> bool:
    """429·5xx 응답, 연결 실패·시간 초과(예외 이름) 이면 True. 그 밖의 HTTP 상태(400 등)는 False."""
    text = str(event)
    if text.isdigit():
        code = int(text)
        return code == 429 or code >= 500
    return True  # 예외 이름(ConnectError, ReadTimeout …), connection_error


def summarize_events(events: Iterable[object]) -> dict:
    events = list(events)
    return {"transport": [e for e in events if is_transport(e)], "other_http": [e for e in events if not is_transport(e)]}


# ── 실행 기록 ──


def _detail(step: dict) -> dict:
    detail = step.get("detail")
    if isinstance(detail, dict):
        return detail
    try:
        value = json.loads(detail or "")
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def submit_stats(steps: list[dict]) -> dict:
    """trace 단계(그 실행 + 아래 일꾼 실행, 기록 순서) → 제출 통계."""
    verdicts = [_detail(s).get("accepted") for s in steps if s.get("kind") == "submit"]
    verdicts = [v for v in verdicts if isinstance(v, bool)]
    return attempts_stats(verdicts)


def attempts_stats(verdicts: list[bool]) -> dict:
    """제출(또는 S 의 답이 온 시도)마다 통과 여부 → 제출 통계."""
    if not verdicts:
        return {"submits": 0, "first_ok": None, "rejections": 0, "recovered_at": None}
    rejections = sum(1 for v in verdicts if not v)
    recovered = None
    if not verdicts[0] and any(verdicts):
        recovered = verdicts.index(True)  # 통과 전까지 거절 수
    return {"submits": len(verdicts), "first_ok": verdicts[0], "rejections": rejections, "recovered_at": recovered}


def classify(source: str | None, steps: list[dict], events: Iterable[object] = (), top_run_id: str | None = None) -> tuple[str, str]:
    """(fail_cause, fail_detail). steps 는 그 사례의 에이전트 실행 단계(아래 일꾼 포함), top_run_id 는 맨 위 실행."""
    if source in SUCCESS_SOURCES:
        return "none", ""
    found = summarize_events(events)
    top = [s for s in steps if top_run_id is None or s.get("run_id") == top_run_id]
    if not top:
        if found["transport"]:
            return "transport", f"실행 기록 없음, 전송 실패 {found['transport']}"
        return "other", "실행 기록 없음"
    ends = [s.get("name") for s in top if s.get("kind") == "end"]
    failed_call = any(s.get("kind") == "llm" and s.get("name") == "failed" for s in top)
    submits = [s for s in top if s.get("kind") == "submit"]
    if "too_many_rejections" in ends:
        return "rejected", f"거절 {sum(1 for s in submits if _detail(s).get('accepted') is False)}번"
    budget = next((e for e in ends if e in BUDGET_ENDS), None)
    if budget:
        return "budget", budget
    if failed_call:
        if found["transport"]:
            return "transport", ", ".join(map(str, found["transport"]))
        if found["other_http"]:
            return "other", f"호출 실패 HTTP {', '.join(map(str, found['other_http']))}"
        return "other", "호출 실패 (까닭 기록 없음)"
    if any(s.get("kind") == "cache" for s in top):
        return "other", "캐시"
    if not submits:
        return "no_submit", "제출 없이 끝남"
    return "budget", "단계 상한"  # 제출은 했지만 상한(max_rejections) 전에 단계가 끝남


def classify_single_call(source: str | None, attempts: list[dict]) -> tuple[str, str]:
    """기준선 S: 시도마다 {"answered": bool, "accepted": bool|None, "event": 상태·예외|None}."""
    if source in SUCCESS_SOURCES:
        return "none", ""
    events = [a["event"] for a in attempts if a.get("event") is not None]
    answered = [a for a in attempts if a.get("answered")]
    if answered and not any(a.get("accepted") for a in answered) and len(answered) == len(attempts):
        return "rejected", f"검사 거절 {len(answered)}번"
    found = summarize_events(events)
    if found["transport"] and not answered:
        return "transport", ", ".join(map(str, found["transport"]))
    if answered and found["transport"]:
        return "rejected", f"검사 거절 {len(answered)}번, 전송 실패 {found['transport']}"
    if found["other_http"]:
        return "other", f"호출 실패 HTTP {', '.join(map(str, found['other_http']))}"
    return "other", "답 없음"


# ── 저장된 결과 폴더 다시 읽기 (호출 없음) ──


def read_steps(trace_db: Path, run_id: str) -> list[dict]:
    """결과 폴더의 harness_trace.db 에서 그 실행 + 아래 일꾼 실행 단계 (읽기 전용)."""
    if not run_id or not Path(trace_db).is_file():
        return []
    conn = sqlite3.connect(f"{Path(trace_db).resolve().as_uri()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("SELECT * FROM steps WHERE run_id = ? OR parent_run_id = ? ORDER BY id", (run_id, run_id)).fetchall()
    except sqlite3.OperationalError:
        rows = []
    finally:
        conn.close()
    return [dict(r) for r in rows]


def usage_events(usage_db: Path, started: str, ended: str, features: Iterable[str] = ()) -> list[object]:
    """결과 폴더의 clova_usage.db 에서 그 시간 사이 실패 호출의 HTTP 상태(없으면 'connection_error').
    예전 결과에는 사례별 전송 기록이 없어 실행 단계의 시각과 에이전트 이름(features)으로 맞춘다
    (같은 에이전트의 다른 사례가 같은 시각에 돌았으면 섞일 수 있다)."""
    features = list(features)
    if not Path(usage_db).is_file():
        return []
    conn = sqlite3.connect(f"{Path(usage_db).resolve().as_uri()}?mode=ro", uri=True)
    try:
        rows = conn.execute("SELECT status, http_status, feature FROM calls WHERE at >= ? AND at <= ? AND status != 'ok' "
                            "AND feature NOT LIKE 'eval_judge%'", (started, ended)).fetchall()
    except sqlite3.OperationalError:
        rows = []
    finally:
        conn.close()
    return [http if http is not None else status for status, http, feature in rows if not features or feature in features]


def reread_case(folder: Path, case: dict) -> tuple[str, str, dict]:
    """저장된 사례 한 줄 → (fail_cause, fail_detail, 제출 통계). 새 결과면 줄에 이미 있는 값을 쓴다."""
    if case.get("fail_cause"):
        return case["fail_cause"], case.get("fail_detail", ""), case.get("submit_stats") or {}
    folder = Path(folder)
    run_id = case.get("run_id")
    steps = read_steps(folder / "harness_trace.db", run_id) if run_id else []
    events: list[object] = []
    if steps and any(s.get("kind") == "llm" and s.get("name") == "failed" for s in steps):
        features = {f"agent:{s['agent']}" for s in steps if s.get("agent")}
        events = usage_events(folder / "clova_usage.db", steps[0]["at"], steps[-1]["at"], features)
    cause, detail = classify(case.get("source"), steps, events, top_run_id=run_id)
    return cause, detail, submit_stats(steps)
