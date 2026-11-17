"""개발자 대시보드 '평가' 탭: 평가 결과 폴더(server/db/app_data/harness_eval/<id>/)를 읽는다. CLOVA 를 부르지 않는다.

스위트마다 result.json 모양이 조금씩 달라 여기서 한 모양으로 맞춘다.
  새 형식(schema 1): metrics[] 에 set(세트 이름)이 붙기도 한다 → 지표 key 는 "id" 또는 "id [set]"
  예전 형식(critic_eval·live_eval: schema 없음, summary·rows) → legacy: true, summary 의 숫자만 지표로
사례 한 줄은 case_id, system, run, run_id, ok(적합·정답 여부, 모르면 None), input(리뷰 원문 등), output, checks,
verdicts(조건별 투표), problems(걸린 까닭), source, seconds 로 맞추고 원래 줄은 raw 에 둔다.

실행 기록(harness_trace.db)은 그 폴더의 파일을 읽기 전용으로 직접 연다. 모양은 Harness/trace.steps_of 와 같다
(전역 TRACE_PATH 를 쓰는 trace.py 는 고치지 않는다).
"""

import json
import re
import sqlite3
from pathlib import Path

from app.core.error_response import ApiError

EVAL_ROOT = Path(__file__).resolve().parents[3] / "db" / "app_data" / "harness_eval"
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
# 실행 목록에 보일 대표 지표 (스위트마다 2~3개). 없으면 앞 지표 2개
HEADLINE = {
    "label": ["negative_recall", "sentiment_macro_f1"],
    "guards": ["missed_rate", "false_reject_rate"],
    "reply": ["reply_fit_rate", "agent_fit_rate", "safety_violation_rate"],
    "batch": ["diagnosis_cause_found", "fit_in_batch", "conflicts_left"],
    "intent": ["intent_accuracy", "wrong_answer_rate"],
}
INPUT_KEYS = ("text", "review_text", "input")
OUTPUT_KEYS = ("output", "reply", "text_out")


# ── 폴더 ──


def folder_of(run_id: str) -> Path:
    """결과 폴더 id → 경로. harness_eval/ 바로 아래 폴더 이름만 받는다 (경로 조작 막기)."""
    if not run_id or not ID_RE.match(run_id) or run_id in (".", ".."):
        raise ApiError(400, "EVAL_BAD_ID", "평가 실행 id 는 결과 폴더 이름만 받아요")
    folder = EVAL_ROOT / run_id
    if folder.resolve().parent != EVAL_ROOT.resolve() or not (folder / "result.json").is_file():
        raise ApiError(404, "EVAL_NOT_FOUND", f"평가 결과가 없어요: {run_id}")
    return folder


def _load(folder: Path) -> dict | None:
    try:
        return json.loads((folder / "result.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


# ── 한 모양으로 맞추기 ──


def metric_key(row: dict) -> str:
    return f"{row['id']} [{row['set']}]" if row.get("set") else str(row["id"])


def _metrics(body: dict) -> list[dict]:
    out = []
    for row in body.get("metrics") or []:
        if not isinstance(row, dict) or "id" not in row:
            continue
        out.append({"key": metric_key(row), "id": row["id"], "set": row.get("set"), "name": row.get("name") or row["id"],
                    "question": row.get("question"), "system": row.get("system"), "value": row.get("value"),
                    "numerator": row.get("numerator"), "denominator": row.get("denominator"), "unit": row.get("unit"),
                    "higher_is_better": row.get("higher_is_better", True), "note": row.get("note") or ""})
    return out


def _legacy_metrics(body: dict) -> list[dict]:
    """예전 형식: summary 의 숫자만 (시스템 구분 없음)."""
    summary = body.get("summary") if isinstance(body.get("summary"), dict) else {}
    out = []
    for name, value in summary.items():
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            out.append({"key": name, "id": name, "set": None, "name": name, "question": None, "system": None, "value": value,
                        "numerator": None, "denominator": None, "unit": None, "higher_is_better": True, "note": ""})
    return out


def _ok(case: dict) -> bool | None:
    for key in ("fit", "correct", "ok", "passed"):
        if isinstance(case.get(key), bool):
            return case[key]
    return None


def _problems(case: dict) -> list[str]:
    out: list[str] = []
    if case.get("error"):
        out.append(f"오류: {case['error']}")
    out += [f"형식: {name}" for name in case.get("format_failures") or []]
    for name, ok in (case.get("conditions") or {}).items():
        if ok is not True and name != "format":
            out.append(f"{name}: {'판단 불가' if ok is None else '실패'}")
    if case.get("wrong"):
        out.append("틀림: " + ", ".join(map(str, case["wrong"])))
    if case.get("why"):
        out.append("까닭: " + ", ".join(map(str, case["why"])))
    if case.get("outcome") in ("missed", "false_reject"):
        out.append({"missed": "놓침", "false_reject": "오거절"}[case["outcome"]])
    if case.get("expected_intent") and case.get("intent") and case.get("correct") is False:
        out.append(f"정답 {case['expected_intent']} → {case['intent']}")
    for name, verdict in (case.get("verdicts") or {}).items():
        if isinstance(verdict, dict) and verdict.get("quote"):
            out.append(f"{name} 문제 문구: {verdict['quote']}")
    out += [f"거절: {reason}" for reason in case.get("rejections") or []]
    return out


def _votes(case: dict) -> dict:
    """조건 → {vote: [True/False/None…], ok}. 심판 투표가 없으면 빈 dict."""
    out = {}
    for name, verdict in (case.get("verdicts") or {}).items():
        if isinstance(verdict, dict):
            out[name] = {"vote": list(verdict.get("vote") or []), "ok": verdict.get("ok"),
                         "reasons": list(verdict.get("reasons") or [])[:3]}
    return out


def normalize_case(case: dict, index: int) -> dict:
    gold = case.get("gold") if isinstance(case.get("gold"), dict) else {}
    expected = case.get("expected_intent") or gold.get("sentiment") or case.get("expected_ok")
    return {
        "index": index,
        "case_id": str(case.get("case_id") or case.get("id") or index),
        "system": case.get("system"),
        "run": case.get("run") or 1,
        "run_id": case.get("run_id"),
        "ok": _ok(case),
        "source": case.get("source"),
        "input": next((case[k] for k in INPUT_KEYS if isinstance(case.get(k), str)), None),
        "output": next((case[k] if isinstance(case[k], str) else json.dumps(case[k], ensure_ascii=False)
                        for k in OUTPUT_KEYS if case.get(k) is not None), None),
        "expected": expected,
        "checks": case.get("checks") or {},
        "verdicts": _votes(case),
        "problems": _problems(case),
        "seconds": case.get("seconds"),
        "raw": case,
    }


def normalize(run_id: str, body: dict) -> dict:
    legacy = "schema" not in body
    suite = body.get("suite") or run_id.split("-", 1)[0]
    if legacy and suite.isdigit():  # live_eval 은 폴더 이름이 시각뿐이다
        suite = "live"
    cases = body.get("cases") if not legacy else body.get("rows") or body.get("cases") or []
    cases = [normalize_case(case, i) for i, case in enumerate(cases if isinstance(cases, list) else []) if isinstance(case, dict)]
    git = body.get("git") or {}
    config = body.get("config") or {}
    return {
        "id": run_id, "suite": suite, "legacy": legacy, "started_at": body.get("started_at") or folder_time(run_id),
        "finished_at": body.get("finished_at"), "git": git, "commit": git.get("commit"), "config": config,
        "baseline": bool(config.get("baseline")), "systems": body.get("systems") or sorted({c["system"] for c in cases if c["system"]}),
        "metrics": _legacy_metrics(body) if legacy else _metrics(body), "cases": cases,
        "tables": body.get("tables") or {}, "validation": body.get("validation") or {},
        "summary": body.get("summary") if legacy else None,
    }


FOLDER_TIME_RE = re.compile(r"(\d{4})(\d{2})(\d{2})-(\d{2})(\d{2})(\d{2})")


def folder_time(run_id: str) -> str | None:
    """폴더 이름의 시각 (예전 형식에는 started_at 이 없다)."""
    found = FOLDER_TIME_RE.search(run_id)
    return "{}-{}-{}T{}:{}:{}+09:00".format(*found.groups()) if found else None


def _started(run: dict) -> str:
    return run.get("started_at") or ""


_CACHE: dict[Path, tuple[float, int, dict]] = {}  # result.json → (고친 시각, 크기, 맞춘 결과). 큰 guards 결과를 매번 읽지 않게


def _read_run(folder: Path) -> dict | None:
    path = folder / "result.json"
    try:
        stat = path.stat()
    except OSError:
        return None
    cached = _CACHE.get(path)
    if cached and cached[:2] == (stat.st_mtime, stat.st_size):
        return cached[2]
    body = _load(folder)
    if body is None:
        return None
    run = normalize(folder.name, body)
    _CACHE[path] = (stat.st_mtime, stat.st_size, run)
    return run


def _all_runs() -> list[dict]:
    if not EVAL_ROOT.is_dir():
        return []
    runs = [run for folder in EVAL_ROOT.iterdir()
            if folder.is_dir() and ID_RE.match(folder.name) and (run := _read_run(folder)) is not None]
    return sorted(runs, key=_started, reverse=True)


# ── API ──


def headline(run: dict) -> list[dict]:
    wanted = HEADLINE.get(run["suite"])
    rows = run["metrics"]
    if wanted:
        picked = [m for name in wanted for m in rows if m["id"] == name]
        seen, out = set(), []
        for m in picked:  # 같은 지표가 세트마다 있으면 시스템마다 첫 줄만
            if (m["id"], m["system"]) not in seen:
                seen.add((m["id"], m["system"]))
                out.append(m)
        if out:
            return out
    return rows[:2]


def list_runs() -> dict:
    runs = _all_runs()
    return {"root": str(EVAL_ROOT), "runs": [
        {"id": r["id"], "suite": r["suite"], "started_at": r["started_at"], "commit": r["commit"], "systems": r["systems"],
         "baseline": r["baseline"], "legacy": r["legacy"], "cases": len(r["cases"]), "headline": headline(r)}
        for r in runs]}


def pairs(cases: list[dict], systems: list[str], limit: int = 50) -> list[dict]:
    """같은 사례·회차의 A 와 B 출력을 나란히 (A·B 를 함께 돌린 실행만)."""
    if not {"A", "B"} <= set(systems):
        return []
    by_key: dict[tuple, dict] = {}
    for case in cases:
        if case["system"] in ("A", "B"):
            by_key.setdefault((case["case_id"], case["run"]), {})[case["system"]] = case
    out = []
    for (case_id, run), both in sorted(by_key.items()):
        if "A" in both and "B" in both:
            a, b = both["A"], both["B"]
            out.append({"case_id": case_id, "run": run, "input": a["input"] or b["input"],
                        "A": {"output": a["output"], "ok": a["ok"], "source": a["source"], "problems": a["problems"]},
                        "B": {"output": b["output"], "ok": b["ok"], "source": b["source"], "problems": b["problems"]},
                        "only": "A" if a["ok"] and not b["ok"] else "B" if b["ok"] and not a["ok"] else None})
    out.sort(key=lambda p: p["only"] is None)  # 한쪽만 맞은 쌍 먼저
    return out[:limit]


def judge_check(run: dict) -> dict | None:
    """심판 검증 카드: guards 의 판정기별 놓침·오거절과 validation. 다른 스위트는 None."""
    if run["suite"] != "guards":
        return None
    rows = [m for m in run["metrics"] if m["id"] in ("missed_rate", "false_reject_rate", "unknown_rate", "agreement_rate")]
    return {"metrics": rows, "validation": run["validation"]}


def get_run(run_id: str, *, failed_only: bool = False, system: str | None = None, limit: int = 100, offset: int = 0) -> dict:
    run = _read_run(folder_of(run_id)) or normalize(run_id, {})
    cases = run["cases"]
    if system:
        cases = [c for c in cases if c["system"] == system]
    if failed_only:
        cases = [c for c in cases if c["ok"] is False or (c["ok"] is None and c["problems"])]
    total = len(cases)
    return {**run, "cases": cases[offset:offset + limit], "cases_total": total, "cases_all": len(run["cases"]),
            "offset": offset, "limit": limit, "pairs": pairs(run["cases"], run["systems"]), "judge_check": judge_check(run)}


def trend(suite: str, metric: str) -> dict:
    """같은 스위트·지표(key)의 실행별 값. 오래된 것부터, 시스템마다 따로."""
    runs = _all_runs()
    points = []
    for run in reversed(runs):
        if run["suite"] != suite:
            continue
        for m in run["metrics"]:
            if m["key"] == metric:
                points.append({"id": run["id"], "started_at": run["started_at"], "commit": run["commit"], "baseline": run["baseline"],
                               "system": m["system"], "value": m["value"], "numerator": m["numerator"],
                               "denominator": m["denominator"], "unit": m["unit"]})
    higher = next((m["higher_is_better"] for r in runs if r["suite"] == suite for m in r["metrics"] if m["key"] == metric), True)
    return {"suite": suite, "metric": metric, "higher_is_better": higher, "points": points}


def trace_steps(run_id: str, agent_run_id: str) -> dict:
    """그 실행 폴더의 harness_trace.db 에서 trace.steps_of 와 같은 모양 (그 실행 + 아래 일꾼 실행, 기록 순서)."""
    path = folder_of(run_id) / "harness_trace.db"
    if not path.is_file():
        return {"id": run_id, "run_id": agent_run_id, "steps": []}
    conn = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("SELECT * FROM steps WHERE run_id = ? OR parent_run_id = ? ORDER BY id",
                            (agent_run_id, agent_run_id)).fetchall()
    except sqlite3.OperationalError:
        rows = []
    finally:
        conn.close()
    return {"id": run_id, "run_id": agent_run_id, "steps": [dict(row) for row in rows]}
