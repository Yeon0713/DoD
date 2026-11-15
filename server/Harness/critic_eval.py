"""LLM 검토(reply_critic.inspect) 정확도를 판정 세트(critic_cases.json)로 잰다. 실제 CLOVA 를 부른다 (1회 사례당 2~5번 호출).

사용 (server/ 에서):
  python -m Harness.critic_eval                    # 1번 돌린다
  python -m Harness.critic_eval --runs 2           # 같은 세트를 2번 돌려 흔들림까지 본다
  python -m Harness.critic_eval --ids b13,b15,b17  # 고친 부분과 관련된 사례만 빨리 본다
  python -m Harness.critic_eval --workers 1        # 예전처럼 하나씩 (기본은 사례 6개를 동시에, CLOVA 동시 호출 2개)

보는 숫자
  놓침    거절해야 할 답글을 통과시킨 수 (가장 중요. 목표 0)
  오탐    올려도 되는 답글을 거절한 수 (목표 10% 이하)
  못 부름 검토 호출이 실패한 수
"""

import argparse
import datetime as dt
import json
import sqlite3
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from app.core import clova_usage_log
from app.core.config import settings
from Harness import limiter, trace

CASES = Path(__file__).parent / "critic_cases.json"
OUT_ROOT = Path(__file__).resolve().parents[1] / "db" / "app_data" / "harness_eval"


def run(runs: int, ids: list[str] | None = None, workers: int = 6) -> dict:
    from Harness.agents import reply_critic
    from Harness.spec import RunContext
    from Harness.tests.fakes import NOW, make_snapshot

    out = OUT_ROOT / ("critic-" + dt.datetime.now().strftime("%Y%m%d-%H%M%S"))
    out.mkdir(parents=True, exist_ok=True)
    clova_usage_log.LOG_PATH = out / "clova_usage.db"
    trace.TRACE_PATH = out / "harness_trace.db"

    cases = json.loads(CASES.read_text(encoding="utf-8"))["cases"]
    if ids:
        unknown_ids = sorted(set(ids) - {case["id"] for case in cases})
        if unknown_ids:
            raise SystemExit(f"판정 세트에 없는 id: {', '.join(unknown_ids)}")
        cases = [case for case in cases if case["id"] in ids]
    rows = []

    def one(n: int, case: dict) -> None:
        ctx = RunContext(snapshot=make_snapshot(), now=NOW, store_facts=case.get("store_facts", []))
        verdict = reply_critic.inspect(
            case["reply"], ctx, review_text=case["review"]["text"],
            has_complaint=bool(case["review"].get("complaints")), regular=case.get("regular", False),
            owner_instruction=case.get("owner_instruction"),
        )
        got = None if verdict is None else verdict.ok
        rows.append({"run": n + 1, "id": case["id"], "expected_ok": case["expected_ok"], "got_ok": got,
                     "kinds": [v.kind for v in verdict.violations] if verdict else None,
                     "why": [v.describe() for v in verdict.violations] if verdict else None})
        mark = "못 부름" if got is None else "맞음" if got == case["expected_ok"] else ("놓침" if got else "오탐")
        print(f"[{n + 1}/{runs}] {case['id']} {mark}", flush=True)

    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=workers) as pool:  # 사례 여러 개를 동시에. CLOVA 동시 호출은 limiter 가 막는다
        for future in [pool.submit(one, n, case) for n in range(runs) for case in cases]:
            future.result()
    rows.sort(key=lambda r: (r["run"], r["id"]))
    with sqlite3.connect(clova_usage_log.LOG_PATH) as conn:
        limited = conn.execute("SELECT COUNT(*) FROM calls WHERE http_status = 429").fetchone()[0]
    print(f"\n전체 {round(time.perf_counter() - started)}초 (사례 {workers}개 동시, CLOVA 동시 호출 {limiter.MAX_CONCURRENT}개), 429 {limited}번")

    bad = [r for r in rows if not r["expected_ok"]]
    good = [r for r in rows if r["expected_ok"]]
    missed = [r for r in bad if r["got_ok"] is True]
    false_reject = [r for r in good if r["got_ok"] is False]
    unknown = [r for r in rows if r["got_ok"] is None]
    summary = {
        "runs": runs, "cases": len(cases),
        "missed": len(missed), "bad_total": len(bad),
        "false_reject": len(false_reject), "good_total": len(good),
        "unknown": len(unknown),
        "missed_ids": dict(Counter(r["id"] for r in missed)),
        "false_reject_ids": dict(Counter(r["id"] for r in false_reject)),
    }
    (out / "result.json").write_text(json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n놓침 {len(missed)}/{len(bad)}  오탐 {len(false_reject)}/{len(good)}  못 부름 {len(unknown)}")
    print("놓친 사례:", summary["missed_ids"])
    print("오탐 사례:", summary["false_reject_ids"])
    for r in false_reject:
        print(f"  오탐 {r['id']}: {r['why']}")
    print(f"기록: {out}")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="LLM 검토 정확도 측정 (실제 CLOVA)")
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--ids", default="", help="쉼표로 구분한 사례 id (비우면 전체)")
    parser.add_argument("--workers", type=int, default=6, help="동시에 돌리는 사례 수 (1 이면 하나씩)")
    parser.add_argument("--concurrency", type=int, default=2, help="CLOVA 동시 호출 한도. 4 는 429 가 많이 났다 (2026-11-15)")
    args = parser.parse_args()
    if not settings.clova_studio_api_key:
        raise SystemExit("server/.env 에 CLOVA_STUDIO_API_KEY 가 없어요")
    limiter.set_max_concurrent(args.concurrency)
    run(args.runs, [i for i in args.ids.split(",") if i] or None, args.workers)


if __name__ == "__main__":
    main()
