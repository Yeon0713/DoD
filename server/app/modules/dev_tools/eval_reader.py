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
    if case.get("part") == "diagnosis" and isinstance(case.get("cause_found"), bool):  # batch 진단: 심은 원인을 찾았나
        return case["cause_found"]
    if case.get("part") == "batch" and isinstance(case.get("left"), bool):  # batch 묶음: 충돌이 남지 않았나
        return not case["left"]
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


_RAW: dict[Path, tuple[float, int, dict]] = {}  # result.json → (고친 시각, 크기, 본문). 맨 위 카드 계산용 (cases 원래 모양)


def _raw_bodies() -> list[dict]:
    """결과 폴더마다 result.json 본문에 _folder 를 붙인 것 (Harness.evals.scorecard 가 받는 모양)."""
    if not EVAL_ROOT.is_dir():
        return []
    out = []
    for folder in EVAL_ROOT.iterdir():
        path = folder / "result.json"
        if not (folder.is_dir() and ID_RE.match(folder.name)):
            continue
        try:
            stat = path.stat()
        except OSError:
            continue
        cached = _RAW.get(path)
        if not (cached and cached[:2] == (stat.st_mtime, stat.st_size)):
            body = _load(folder)
            if not isinstance(body, dict):
                continue
            cached = (stat.st_mtime, stat.st_size, {**body, "_folder": folder})
            _RAW[path] = cached
        out.append(cached[2])
    return out


def parse_picks(text: str | None) -> dict[str, str]:
    """"q3.missed_compensation:guards-…,q5.turn_briefing:voice-…" → {지표 key: 결과 폴더}. 모르는 key·이상한 폴더는 버린다."""
    from Harness.evals import scorecard

    picks = {}
    for part in (text or "").split(","):
        key, _, run_id = part.strip().partition(":")
        if key in scorecard.ITEM_BY_KEY and ID_RE.match(run_id or ""):
            picks[key] = run_id
    return picks


def scorecard_view(picks: dict[str, str] | None = None) -> dict:
    """평가 탭 맨 위 질문 1~5 카드. summary(마크다운)와 같은 계산(Harness.evals.scorecard)이다."""
    from Harness.evals import scorecard

    return scorecard.scorecard(_raw_bodies(), picks)


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
    return {"root": str(EVAL_ROOT), "summary": summary(runs), "runs": [
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


def get_run(run_id: str, *, failed_only: bool = False, system: str | None = None, limit: int = 100, offset: int = 0,
            case: int | None = None) -> dict:
    run = _read_run(folder_of(run_id)) or normalize(run_id, {})
    cases = run["cases"]
    if case is not None:  # 사례 격자에서 누른 칸 하나
        cases = [c for c in cases if c["index"] == case]
    if system:
        cases = [c for c in cases if c["system"] == system]
    if failed_only:
        cases = [c for c in cases if c["ok"] is False or (c["ok"] is None and c["problems"])]
    total = len(cases)
    return {**run, "cases": cases[offset:offset + limit], "cases_total": total, "cases_all": len(run["cases"]),
            "offset": offset, "limit": limit, "pairs": pairs(run["cases"], run["systems"]), "judge_check": judge_check(run),
            "charts": charts(run, folder_of(run_id))}


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


# ── 그래프용 집계 (화면은 그리기만 한다) ──
# get_run 의 charts: 질문(1~5)마다 그 실행에서 그릴 수 있는 그래프 묶음과 사례 격자(cases_grid).
# list_runs 의 summary: 질문마다 가장 최근 실행의 대표 지표, 시스템별 값, A·B 차이, 목표 통과 여부.

SUMMARY = [  # (질문, 스위트, 지표 id, 세트)
    (1, "label", "negative_recall", "balanced"),
    (2, "reply", "reply_fit_rate", None),
    (3, "guards", "missed_rate", "all"),
    (4, "reply", "task_completion_rate", None),
    (5, "reply", "prep_within_budget", None),
]
# 목표: 기준 문서에 숫자 목표가 없어 코드에 있는 것만 쓴다.
#   guards → critic 기준(놓침 0, 오거절 10% 이하, guards_eval.critic_target) / A·B 지표 → B 가 A 보다 나쁘지 않음
GOAL_NOTES = {"ab": "B(하네스)가 A(단일)보다 나쁘지 않음", "critic": "LLM 검토기 기준: 놓침 0, 오거절 10% 이하 (전체 세트)",
              "none": "기준 없음 (비교만)"}
STATUS_FIXED = {"AGENT": "good", "SINGLE_CALL": "good2", "FALLBACK": "warning", "TEMPLATE": "serious", "NONE": "critical"}
SOURCES = ["AGENT", "SINGLE_CALL", "FALLBACK", "TEMPLATE", "NONE"]
# 결과 구성: 생성이 성공했으면 적합 여부로, 아니면 실패 원인(Harness/evals/fail_cause)으로 나눈다
OUTCOME_ORDER = [("success_fit", "good"), ("success_unfit", "good2"), ("transport", "neutral"), ("rejected", "critical"),
                 ("budget", "serious"), ("no_submit", "warning"), ("other", "neutral2")]
OUTCOME_SUITES = ("reply", "batch")
TOP_REASONS = 8
GRID_ROWS = 300
LATENCY_BUDGET = {"reply": "prep_budget_seconds", "intent": "judge_budget_seconds"}
DEFAULT_BUDGET = {"reply": 15}  # 예산을 config 에 적기 전 결과는 기준 문서 v2 의 15초로 본다


def _metric(run: dict, metric_id: str, system: str | None, set_name: str | None = None) -> dict | None:
    return next((m for m in run["metrics"] if m["id"] == metric_id and m["system"] == system
                 and (set_name is None or m.get("set") in (set_name, None))), None)


def _num(m: dict | None) -> dict | None:
    if m is None:
        return None
    return {"value": m["value"], "numerator": m["numerator"], "denominator": m["denominator"], "unit": m["unit"]}


def _better_or_same(a: dict | None, b: dict | None, higher: bool) -> bool | None:
    if not a or not b or a["value"] is None or b["value"] is None:
        return None
    return b["value"] >= a["value"] if higher else b["value"] <= a["value"]


def summary(runs: list[dict]) -> list[dict]:
    """질문마다 카드 하나. 그 스위트의 가장 최근(예전 형식 제외) 실행에서 뽑는다. 없으면 run 이 None."""
    out = []
    for question, suite, metric_id, set_name in SUMMARY:
        run = next((r for r in runs if r["suite"] == suite and not r["legacy"]), None)
        card = {"question": question, "suite": suite, "metric": metric_id, "set": set_name, "run": run["id"] if run else None,
                "name": None, "higher_is_better": True, "values": {}, "diff": None, "goal": None, "goal_note": None}
        if run:
            rows = [m for m in run["metrics"] if m["id"] == metric_id and (set_name is None or m.get("set") in (set_name, None))]
            if rows:
                card["name"], card["higher_is_better"] = rows[0]["name"], rows[0]["higher_is_better"]
            for m in rows:
                card["values"][m["system"] or "-"] = _num(m)
            a, b = card["values"].get("A"), card["values"].get("B")
            if a and b and a["value"] is not None and b["value"] is not None:
                card["diff"] = b["value"] - a["value"]
            if suite == "guards":
                target = (run["validation"].get("critic_target") or {}).get(set_name or "all")
                card["goal"], card["goal_note"] = (target or {}).get("pass"), GOAL_NOTES["critic"]
            elif a and b:
                card["goal"], card["goal_note"] = _better_or_same(a, b, card["higher_is_better"]), GOAL_NOTES["ab"]
            else:
                card["goal_note"] = GOAL_NOTES["none"]
        out.append(card)
    return out


# ── 질문 1: 분류 ──


def _recall_precision(run: dict) -> dict | None:
    sets = [s for s in ("balanced", "full") if any(m.get("set") == s for m in run["metrics"])]
    if not sets:
        return None
    out = {}
    for set_name in sets:
        rows = {}
        for system in run["systems"]:
            recall = _metric(run, "negative_recall", system, set_name)
            precision = _metric(run, "negative_precision", system, set_name)
            if recall or precision:
                rows[system] = {"recall": _num(recall), "precision": _num(precision)}
        if rows:
            out[set_name] = rows
    return {"sets": out, "default": sets[0]} if out else None


def _confusion(run: dict) -> dict | None:
    table = run["tables"].get("confusion")
    if not isinstance(table, dict) or not table:
        return None
    return {"sets": table, "default": "balanced" if "balanced" in table else next(iter(table))}


# ── 질문 2: 글 ──


def _conditions(run: dict) -> dict | None:
    """조건별 통과율 (시스템마다). A·B 덤벨과 사례 격자가 같이 쓴다."""
    names: list[str] = []
    out: dict[str, dict[str, dict[str, int]]] = {}
    for case in run["cases"]:
        conditions = case["raw"].get("conditions") or {name: v.get("ok") for name, v in case["verdicts"].items()}
        for name, ok in conditions.items():
            if name not in names:
                names.append(name)
            cell = out.setdefault(case["system"] or "-", {}).setdefault(name, {"pass": 0, "fail": 0, "unknown": 0})
            cell["pass" if ok is True else "fail" if ok is False else "unknown"] += 1
    if not names:
        return None
    for system_cells in out.values():
        for cell in system_cells.values():
            total = cell["pass"] + cell["fail"] + cell["unknown"]
            cell["total"], cell["rate"] = total, (cell["pass"] / total) if total else None
    return {"conditions": names, "systems": out}


def _outcome_mix(run: dict, folder: Path | None) -> dict | None:
    """시스템마다 사례 구성: 생성 성공·적합 / 생성 성공·부적합 / 실패 원인별. fail_cause 가 없는 예전 결과는
    그 폴더의 harness_trace.db·clova_usage.db 를 읽어 같은 규칙으로 가른다 (호출 없음). 기준선 R(규칙)은 뺀다."""
    if run["suite"] not in OUTCOME_SUITES or folder is None:
        return None
    from Harness.evals import fail_cause

    out: dict[str, dict[str, int]] = {}
    for case in run["cases"]:
        raw = case["raw"]
        if raw.get("part") == "batch" or raw.get("source") == "RULE" or not raw.get("source"):
            continue
        cause = fail_cause.reread_case(folder, raw)[0]
        key = (("success_fit" if case["ok"] else "success_unfit") if cause == "none" else cause)
        row = out.setdefault(case["system"] or "-", {})
        row[key] = row.get(key, 0) + 1
    if not out:
        return None
    return {"order": [{"key": k, "status": st} for k, st in OUTCOME_ORDER], "systems": out}


def _source_mix(run: dict) -> dict | None:
    """source_rate 지표로 결과 구성 (AGENT·FALLBACK·TEMPLATE·NONE 건수)."""
    out = {}
    for system in run["systems"]:
        counts = {}
        agent = _metric(run, "task_completion_rate", system)
        if agent and agent["numerator"] is not None:
            counts["AGENT"] = agent["numerator"]
        for source in SOURCES[1:]:
            m = _metric(run, f"source_rate:{source}", system)
            if m and m["numerator"] is not None:
                counts[source] = m["numerator"]
        if counts:
            total = (agent or {}).get("denominator") or sum(counts.values())
            out[system] = {"counts": counts, "total": total}
    if not out:
        return None
    return {"order": [{"key": s, "status": STATUS_FIXED[s]} for s in SOURCES], "systems": out}


# ── 질문 3: 안전장치 ──


def _guards_scatter(run: dict) -> dict | None:
    sets = [s for s in ("all", "gold", "critic_cases") if any(m.get("set") == s for m in run["metrics"])]
    if run["suite"] != "guards" or not sets:
        return None
    points = {}
    for set_name in sets:
        rows = []
        for system in run["systems"]:
            missed = _metric(run, "missed_rate", system, set_name)
            false_reject = _metric(run, "false_reject_rate", system, set_name)
            if missed and false_reject and missed["value"] is not None and false_reject["value"] is not None:
                rows.append({"system": system, "missed": _num(missed), "false_reject": _num(false_reject)})
        if rows:
            points[set_name] = rows
    if not points:
        return None
    return {"sets": points, "default": next(s for s in sets if s in points), "target": {"missed": 0.0, "false_reject": 0.10, "note": GOAL_NOTES["critic"]}}


def _by_kind(run: dict) -> dict | None:
    table = run["tables"].get("by_kind")
    if not isinstance(table, dict) or not table:
        return None
    kinds = [k for rows in table.values() for k in rows if k != "normal"]
    kinds = list(dict.fromkeys(kinds))
    cells = {}
    for system, rows in table.items():
        for kind in kinds:
            c = rows.get(kind)
            if c:
                total = c.get("total") or 0
                cells.setdefault(system, {})[kind] = {"missed": c.get("missed", 0), "total": total, "unknown": c.get("unknown", 0),
                                                      "rate": (c.get("missed", 0) / total) if total else None}
    return {"kinds": kinds, "systems": cells}


# ── 질문 4: 동작 ──


def _pass_distribution(run: dict) -> dict | None:
    """사례마다 몇 회차에 맞았나 (0~회차 수). 시스템마다 그 분포."""
    if run["suite"] == "label":  # label 결과는 틀린 사례만 남겨 분포가 뜻이 없다
        return None
    by_case: dict[tuple, list[bool]] = {}
    for case in run["cases"]:
        if case["ok"] is None:
            continue
        by_case.setdefault((case["system"] or "-", case["case_id"]), []).append(bool(case["ok"]))
    if not by_case:
        return None
    runs = max(len(v) for v in by_case.values())
    out = {}
    for (system, _), oks in by_case.items():
        row = out.setdefault(system, [0] * (runs + 1))
        row[sum(oks)] += 1
    return {"runs": runs, "systems": out}


def _batch_grid(run: dict) -> dict | None:
    if run["suite"] != "batch":
        return None
    rows: dict[str, dict] = {}
    for case in run["cases"]:
        key = f"{case['case_id']} · {case['raw'].get('part', '')}".strip(" ·")
        rows.setdefault(key, {})[f"{case['system']}#{case['run']}"] = {"ok": case["ok"], "index": case["index"]}
    columns = sorted({col for cells in rows.values() for col in cells})
    return {"rows": [{"key": k, "cells": v} for k, v in sorted(rows.items())], "columns": columns}


def _reasons(run: dict) -> dict | None:
    out = {}
    for case in run["cases"]:
        for reason in case["raw"].get("rejections") or []:
            label = re.sub(r"'[^']*'", "'…'", str(reason))[:60]
            row = out.setdefault(case["system"] or "-", {})
            row[label] = row.get(label, 0) + 1
    if not out:
        return None
    return {"systems": {s: [{"label": k, "count": n} for k, n in sorted(r.items(), key=lambda kv: -kv[1])[:TOP_REASONS]]
                        for s, r in out.items()}}


# ── 질문 5: 비용·시간 ──


def _latency(run: dict) -> dict | None:
    seconds = {}
    for case in run["cases"]:
        value = case.get("seconds")
        if isinstance(value, (int, float)) and value > 0:
            seconds.setdefault(case["system"] or "-", []).append(round(float(value), 2))
    if not seconds:
        return None
    budget = run["config"].get(LATENCY_BUDGET.get(run["suite"], ""), DEFAULT_BUDGET.get(run["suite"]))
    return {"budget": budget, "systems": seconds}


def _cost(run: dict) -> dict | None:
    out = {}
    for metric_id in ("calls_per_fit", "tokens_per_fit"):
        rows = {s: _num(_metric(run, metric_id, s)) for s in run["systems"]}
        rows = {s: v for s, v in rows.items() if v and v["value"] is not None}
        if rows:
            out[metric_id] = rows
    return out or None


# ── 사례 격자 ──


def _cases_grid(run: dict) -> dict | None:
    """사례(사례 id·시스템·회차) × 조건 통과/실패. 칸을 누르면 그 사례(index)를 연다."""
    conditions = (_conditions(run) or {}).get("conditions")
    if not conditions:
        return None
    rows = []
    for case in run["cases"]:
        values = case["raw"].get("conditions") or {name: v.get("ok") for name, v in case["verdicts"].items()}
        if not values:
            continue
        rows.append({"index": case["index"], "case_id": case["case_id"], "system": case["system"], "run": case["run"],
                     "ok": case["ok"], "cells": [values.get(name) for name in conditions]})
    rows.sort(key=lambda r: (r["ok"] is not False, r["case_id"], r["system"] or "", r["run"]))  # 실패 먼저
    return {"conditions": conditions, "rows": rows[:GRID_ROWS], "total": len(rows)}


def charts(run: dict, folder: Path | None = None) -> dict:
    return {
        "q1": {"recall_precision": _recall_precision(run), "confusion": _confusion(run)},
        "q2": {"conditions": _conditions(run), "source_mix": _source_mix(run), "outcome_mix": _outcome_mix(run, folder)},
        "q3": {"scatter": _guards_scatter(run), "by_kind": _by_kind(run)},
        "q4": {"pass_distribution": _pass_distribution(run), "batch_grid": _batch_grid(run), "reasons": _reasons(run)},
        "q5": {"latency": _latency(run), "cost": _cost(run)},
        "cases_grid": _cases_grid(run),
    }
