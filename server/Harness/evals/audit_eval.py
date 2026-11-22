"""감사팀 2차 감사 판정 정확도 (donna-voice/docs/audit-team-plan.md 13장). 실제 CLOVA 를 부른다.

python -m Harness.evals audit [--runs 2] [--ids …] [--job negative_reply]
- 기존 답글 기준 6개(reply_critic)는 Harness/critic_cases.json 을 그대로 쓴다 (job "reply", 기준 "critic"). 숫자가 critic_eval 과 같아야 한다.
- 새 기준은 Harness/evals/data/audit_cases.json (판정 코드가 생기는 5단계부터 돈다). 사례 모양 {id, job, criterion, input, output, expected_ok}.
보는 숫자 (기준마다): 놓침(걸려야 하는 것을 통과) 목표 5% 이하, 오탐(걸리면 안 되는 것을 걸음) 목표 10% 이하, 못 부름, 흔들림(--runs 2 이상).
"""

import argparse
import json
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from Harness import critic_eval
from Harness.evals import report

DATA = Path(__file__).parent / "data" / "audit_cases.json"
MISS_GOAL, FALSE_GOAL = 0.05, 0.10  # 결정 14


def load_cases(ids: list[str] | None = None, job: str | None = None) -> list[dict]:
    critic = json.loads(critic_eval.CASES.read_text(encoding="utf-8"))["cases"]
    cases = [{**case, "job": "reply", "criterion": "critic"} for case in critic]
    if ids:
        cases = [c for c in cases if c["id"] in ids]
    if job:
        cases = [c for c in cases if c["job"] == job]
    return cases


def judge(case: dict, ctx) -> bool | None:
    """합격이면 True, 불합격 False, 판정 못 함 None."""
    if case["criterion"] == "critic":
        from Harness.agents import reply_critic

        verdict = reply_critic.inspect(
            case["reply"], ctx, review_text=case["review"]["text"], has_complaint=bool(case["review"].get("complaints")),
            regular=case.get("regular", False), owner_instruction=case.get("owner_instruction"),
        )
        return None if verdict is None else verdict.ok
    raise ValueError(f"모르는 기준: {case['criterion']}")


def summarize(rows: list[dict]) -> list[dict]:
    """기준마다 놓침·오탐·못 부름·흔들림."""
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in rows:
        groups[(row["job"], row["criterion"])].append(row)
    out = []
    for (job, criterion), found in sorted(groups.items()):
        bad = [r for r in found if not r["expected_ok"]]
        good = [r for r in found if r["expected_ok"]]
        missed = sum(1 for r in bad if r["got_ok"] is True)
        false = sum(1 for r in good if r["got_ok"] is False)
        by_id: dict[str, set] = defaultdict(set)
        for r in found:
            by_id[r["id"]].add(r["got_ok"])
        runs = max((r["run"] for r in found), default=1)
        miss_rate = missed / len(bad) if bad else 0.0
        false_rate = false / len(good) if good else 0.0
        out.append({
            "job": job, "criterion": criterion, "missed": missed, "bad_total": len(bad), "false_reject": false,
            "good_total": len(good), "unknown": sum(1 for r in found if r["got_ok"] is None),
            "unstable": sum(1 for v in by_id.values() if len(v) > 1) if runs > 1 else None,
            "meets_goal": miss_rate <= MISS_GOAL and false_rate <= FALSE_GOAL,
        })
    return out


def run(args: argparse.Namespace) -> list[dict]:
    from Harness.spec import RunContext
    from Harness.tests.fakes import NOW, make_snapshot

    ids = [part for part in args.ids.split(",") if part] or None
    cases = load_cases(ids, getattr(args, "job", None))
    eval_run = report.start("audit", config={"data": {"file": DATA.name, "sha256": report.file_sha256(DATA)}, "runs": args.runs},
                            systems=["audit"])
    report.disable_cache()  # 같은 글을 여러 번 판정해 흔들림을 보므로 판정 캐시를 쓰지 않는다
    rows: list[dict] = []

    def one(n: int, case: dict) -> None:
        facts = case.get("store_facts") or case.get("input", {}).get("facts") or []
        ctx = RunContext(snapshot=make_snapshot(), now=NOW, store_facts=facts)
        got = judge(case, ctx)
        rows.append({"run": n + 1, "id": case["id"], "job": case["job"], "criterion": case["criterion"],
                     "expected_ok": case["expected_ok"], "got_ok": got})
        mark = "못 부름" if got is None else "맞음" if got == case["expected_ok"] else ("놓침" if got else "오탐")
        print(f"[{n + 1}/{args.runs}] {case['id']} {mark}", flush=True)

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for future in [pool.submit(one, n, case) for n in range(args.runs) for case in cases]:
            future.result()
    rows.sort(key=lambda r: (r["run"], r["id"]))
    summary = summarize(rows)
    for row in rows:
        eval_run.add_case(row)
    for row in summary:
        eval_run.add_metric(row)
        mark = "목표 넘음" if row["meets_goal"] else "목표 못 넘음"
        print(f"{row['job']:<16} {row['criterion']:<16} 놓침 {row['missed']}/{row['bad_total']}  "
              f"오탐 {row['false_reject']}/{row['good_total']}  못 부름 {row['unknown']}  {mark}")
    print(f"기록: {eval_run.finish().parent}")
    return summary
