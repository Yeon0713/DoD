"""평가 결과(result.json)들을 모아 보고서 마크다운 하나로 쓴다. CLOVA 를 부르지 않는다.

python -m Harness.evals report [--results 폴더1,폴더2,…] [--out 보고서.md]
  --results 를 비우면 결과 폴더 뿌리(report.OUT_ROOT)에서 스위트마다 가장 최근 폴더를 고른다
  (--baseline 이면 config.baseline 이 true 인 것 중 가장 최근).
  --out 을 비우면 지금 폴더에 report-<YYYY-MM-DD>.md 를 쓴다. 저장소 안에는 쓰지 않는다 (작업 공간 폴더를 준다).

차례
  1. 계획 문서와 다른 점 (맨 위): 정의를 바꾼 것(고정 목록) + 안 돌린 스위트 + 값을 못 낸 지표
  2. 실행: 스위트마다 결과 폴더, 시작 시각, 커밋, 기준점, 정답지 판 번호와 해시
  3. 질문 1~5: 지표 × 시스템 표 (분자/분모와 값). 짝 비교(paired_*)도 이 표에 든다
  4. 가장 많이 걸린 거절 이유 (스위트·시스템마다 3개)
  5. 실패 사례 하나씩 (스위트·시스템마다, 사례 id 와 까닭. 리뷰 글은 넣지 않는다)
  6. 심판 검증 (guards 의 judge_* 지표)
"""

import argparse
import datetime as dt
import json
from collections import Counter
from pathlib import Path

from Harness.evals import report

SUITES = ("label", "guards", "reply", "batch", "intent")
QUESTIONS = {
    1: "질문 1. 리뷰를 바르게 가르는가",
    2: "질문 2. 글을 믿을 수 있는가",
    3: "질문 3. 안전장치가 제 역할을 하는가",
    4: "질문 4. 에이전트가 믿을 만하게 동작하는가",
    5: "질문 5. 비용과 시간",
}
# 기준 문서("도나 신뢰성 평가 계획" v2)와 정의가 다른 것. 바꾸면 여기에 적는다
PLAN_DIFFERENCES = [
    "reply: 문서 지표 reply_fit_rate 외에 agent_fit_rate(AGENT 이면서 적합)를 추가 지표로 함께 싣는다.",
    "reply: 주 실험은 서버 경로(reply_agent.draft 대 single_agent), 음성 경로(--path voice)는 보조 실험이다.",
    "intent: A/B 비교가 아니라 rule 과 rule+judge 를 비교한다. judge_within_budget(3초 안 비율)을 더했다.",
]
FAILURE_SNIPPET = 80


def latest_folders(root: Path, baseline: bool = False) -> dict[str, Path]:
    found: dict[str, Path] = {}
    for suite in SUITES:
        for folder in sorted(root.glob(f"{suite}-*"), reverse=True):
            result = folder / "result.json"
            if not result.exists():
                continue
            if baseline and not json.loads(result.read_text(encoding="utf-8")).get("config", {}).get("baseline"):
                continue
            found[suite] = folder
            break
    return found


def load(folders: list[Path]) -> dict[str, dict]:
    out = {}
    for folder in folders:
        body = json.loads((Path(folder) / "result.json").read_text(encoding="utf-8"))
        out[body["suite"]] = {**body, "_folder": str(folder)}
    return out


def fmt(metric: dict) -> str:
    value = metric.get("value")
    if value is None:
        return f"못 냄 ({metric.get('note') or '값 없음'})"
    if metric.get("unit") == "ratio":
        return f"{metric['numerator']}/{metric['denominator']} ({value:.1%})"
    shown = f"{value:.2f}" if isinstance(value, float) else str(value)
    return f"{shown} {metric.get('unit') or ''}".strip()


def metric_table(rows: list[dict]) -> list[str]:
    systems = list(dict.fromkeys(row.get("system") or "-" for row in rows))
    keys = list(dict.fromkeys((row["id"], row["name"]) for row in rows))
    cell = {(row["id"], row.get("system") or "-"): row for row in rows}
    lines = ["| 지표 | " + " | ".join(systems) + " |", "|---|" + "---|" * len(systems)]
    for metric_id, name in keys:
        values = [fmt(cell[(metric_id, s)]) if (metric_id, s) in cell else "-" for s in systems]
        arrow = "" if next(r for r in rows if r["id"] == metric_id).get("higher_is_better", True) else " (낮을수록 좋음)"
        lines.append(f"| {name} `{metric_id}`{arrow} | " + " | ".join(values) + " |")
    return lines


def failure_reason(case: dict) -> str | None:
    """실패면 짧은 까닭, 아니면 None."""
    if case.get("error"):
        return f"오류: {str(case['error'])[:FAILURE_SNIPPET]}"
    if case.get("fit") is False:
        bad = [name for name, ok in (case.get("conditions") or {}).items() if ok is not True]
        return "부적합: " + ", ".join(bad or ["출력 없음"]) + (f" (형식: {', '.join(case['format_failures'])})"
                                                              if case.get("format_failures") else "")
    if case.get("correct") is False:
        return f"정답 {case.get('expected_intent')} → {case.get('intent')}"
    return None


def build(results: dict[str, dict], *, today: dt.date, baseline: bool = False) -> str:
    lines = [f"# 도나 신뢰성 평가 보고 ({today:%Y-%m-%d})", ""]
    if baseline:
        lines += ["기준점 실행(config.baseline) 결과로 썼다.", ""]

    # 1. 계획 문서와 다른 점
    missing = [suite for suite in SUITES if suite not in results]
    unmade = [f"{body['suite']} {m.get('system') or '-'} `{m['id']}`" for body in results.values()
              for m in body.get("metrics", []) if m.get("value") is None]
    lines += ["## 계획 문서와 다른 점", ""]
    lines += [f"- {text}" for text in PLAN_DIFFERENCES]
    lines += [f"- 안 돌림: {', '.join(missing)}" if missing else "- 안 돌린 스위트 없음"]
    lines += [f"- 값을 못 낸 지표: {', '.join(unmade)}" if unmade else "- 값을 못 낸 지표 없음"]
    lines.append("")

    # 2. 실행
    lines += ["## 실행", "", "| 스위트 | 결과 폴더 | 시작 | 커밋 | 기준점 | 정답지 |", "|---|---|---|---|---|---|"]
    for suite in SUITES:
        body = results.get(suite)
        if body is None:
            lines.append(f"| {suite} | 안 돌림 | | | | |")
            continue
        git = body.get("git") or {}
        config = body.get("config") or {}
        gold = config.get("gold") or config.get("data") or {}
        gold_text = f"{gold.get('file', '')} {str(gold.get('sha256', ''))[:12]}".strip() or "-"
        commit = f"{str(git.get('commit') or '')[:8]}{' (고친 파일 있음)' if git.get('dirty') else ''}"
        lines.append(f"| {suite} | `{Path(body['_folder']).name}` | {body.get('started_at', '')} | {commit} | "
                     f"{'예' if config.get('baseline') else ''} | {gold_text} |")
    lines.append("")

    # 3. 질문별
    every = [{**m, "_suite": body["suite"]} for body in results.values() for m in body.get("metrics", [])]
    for number, title in QUESTIONS.items():
        lines += [f"## {title}", ""]
        rows = [m for m in every if m.get("question") == number]
        if not rows:
            lines += ["안 돌림", ""]
            continue
        for suite in SUITES:
            part = [m for m in rows if m["_suite"] == suite]
            if part:
                lines += [f"### {suite}", ""] + metric_table(part) + [""]

    # 4. 거절 이유
    lines += ["## 가장 많이 걸린 거절 이유", ""]
    any_reason = False
    for suite, body in results.items():
        by_system: dict[str, Counter] = {}
        for case in body.get("cases", []):
            for reason in case.get("rejections") or []:
                by_system.setdefault(case.get("system") or "-", Counter())[str(reason)[:FAILURE_SNIPPET]] += 1
        for system, counter in by_system.items():
            any_reason = True
            top = "; ".join(f"{reason} ({count})" for reason, count in counter.most_common(3))
            lines.append(f"- {suite} {system}: {top}")
    lines += ([] if any_reason else ["- 거절 기록 없음"]) + [""]

    # 5. 실패 사례
    lines += ["## 실패 사례 (스위트·시스템마다 하나)", ""]
    any_failure = False
    for suite, body in results.items():
        seen = set()
        for case in body.get("cases", []):
            system = case.get("system") or "-"
            reason = failure_reason(case)
            if reason is None or system in seen:
                continue
            seen.add(system)
            any_failure = True
            lines.append(f"- {suite} {system} `{case.get('case_id')}`: {reason}")
    lines += ([] if any_failure else ["- 실패 사례 없음"]) + [""]

    # 6. 심판 검증
    lines += ["## 심판 검증", ""]
    judge_rows = [m for m in (results.get("guards") or {}).get("metrics", []) if str(m.get("system") or "").startswith("judge")]
    lines += (metric_table(judge_rows) if judge_rows else ["안 돌림 (guards 의 judge_* 결과 없음)"]) + [""]
    return "\n".join(lines)


def run(args: argparse.Namespace) -> Path:
    baseline = bool(getattr(args, "baseline", False))
    if getattr(args, "results", ""):
        folders = [Path(part) for part in args.results.split(",") if part]
    else:
        folders = list(latest_folders(report.OUT_ROOT, baseline).values())
    results = load(folders)
    today = report.real_now().date()
    out = Path(getattr(args, "out", None) or f"report-{today:%Y-%m-%d}.md")
    out.write_text(build(results, today=today, baseline=baseline), encoding="utf-8")
    print(f"보고서: {out.resolve()} (스위트 {', '.join(results) or '없음'})")
    return out
