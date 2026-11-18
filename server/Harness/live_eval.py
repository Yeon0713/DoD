"""실제 CLOVA 로 에이전트 성공률을 잰다. CLOVA 호출 비용이 든다 (전체 5회 기준 약 200~300원).

사용 (server/ 에서):
  python -m Harness.live_eval --runs 5
  python -m Harness.live_eval --runs 3 --only campaign,supervisor
  python -m Harness.live_eval --runs 5 --workers 1     # 예전처럼 하나씩 (기본은 사례 4개를 동시에)

- 데이터는 테스트와 같은 가상 가게 t001 (Harness/tests/fakes.py). 실제 매장 DB 는 건드리지 않는다.
- 사례 여러 개를 동시에 돌린다 (--workers, --concurrency). 측정 중에는 캐시를 쓰지 않는다 (동시에 도는 같은 사례가 서로의 캐시를 가져가지 않게).
  호출 수는 사례마다 직접 센다. 걸린 초에는 동시 한도 자리를 기다린 시간이 섞일 수 있다.
- 사례마다 새로 돌린다. 결과는 source 로 센다: AGENT(에이전트 성공), FALLBACK(기존 방식으로 물러남), NONE(결과 없음)
- 기록(CLOVA 사용 기록, 실행 기록, 결과 JSON)은 db/app_data/harness_eval/<시각>/ 에 남는다 (git 에 올라가지 않는다).
  기존 개발자 대시보드 기록에는 섞지 않는다.
"""

import argparse
import datetime as dt
import json
import sqlite3
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx

from app.core import clova_usage_log
from app.core.config import settings
from Harness import cache, limiter, trace

OUT_ROOT = Path(__file__).resolve().parents[1] / "db" / "app_data" / "harness_eval"


def _cases():
    from Harness.agents import campaign_agent, complaint_agent, reply_agent
    from Harness.spec import Proposal
    from Harness.supervisor import coordinate_batch

    def item(ctx, plan_id):
        return next(i for i in ctx.snapshot.plan.plan_items if i.plan_id == plan_id)

    def fixed_proposals():
        """supervisor 사례용: 충돌 3종이 다 나오는 고정 제안 (일꾼을 매번 다시 돌리지 않으려고)."""
        def p(plan_id, **content):
            return Proposal("fixed", plan_id, content, "AGENT", "fixed")

        return {
            "REVISIT_REPLY:r1:2026-11-15": p("REVISIT_REPLY:r1:2026-11-15", kind="REPLY", text="국물이 싱거우셨다니 죄송합니다. 간을 다시 보겠습니다."),
            "REVISIT_REPLY:r4:2026-11-15": p("REVISIT_REPLY:r4:2026-11-15", kind="REPLY", text="비빔국수 양념을 알아봐 주셔서 감사해요."),
            "REORDER_NUDGE:c1:2026-11-15": p("REORDER_NUDGE:c1:2026-11-15", kind="NUDGE", text="이번 주말엔 비빔국수 어떠세요?"),
            "REVIEW_FIX:risk_001:2026-11-15": p("REVIEW_FIX:risk_001:2026-11-15", risk_id="risk_001", confidence="high", checklist=[],
                                                hypotheses=[{"text": "불만 3건 모두 19시(오후 7시) 주문이고 그때 근무는 1명이에요", "evidence": ["get_orders_by_hour"]}]),
            "POSTER:e1:2026-11-21": p("POSTER:e1:2026-11-21", theme="축제", menu_ids=["m1", "m3"], reason="따끈해요.", ments=[]),
        }

    return {
        "reply_complaint": lambda ctx: reply_agent.draft(item(ctx, "REVISIT_REPLY:r1:2026-11-15"), ctx),
        "reply_praise": lambda ctx: reply_agent.draft(item(ctx, "REVISIT_REPLY:r4:2026-11-15"), ctx),
        "nudge": lambda ctx: reply_agent.draft(item(ctx, "REORDER_NUDGE:c1:2026-11-15"), ctx),
        "rewrite": lambda ctx: reply_agent.rewrite(
            "국물이 싱거우셨다니 죄송합니다. 12월부터 국물 간을 다시 맞추겠습니다.", ctx,
            instruction="다음 주문 때 만두 서비스 드린다고 덧붙여 줘", review_id="r1"),
        "complaint": lambda ctx: complaint_agent.diagnose(item(ctx, "REVIEW_FIX:risk_001:2026-11-15"), ctx),
        "campaign": lambda ctx: campaign_agent.plan_campaign(item(ctx, "POSTER:e1:2026-11-21"), ctx),
        "supervisor": lambda ctx: coordinate_batch(list(fixed_proposals()), fixed_proposals(), ctx),
    }


def _tokens(path: Path) -> tuple[int, int]:
    with sqlite3.connect(path) as conn:
        row = conn.execute("SELECT COALESCE(SUM(input_tokens), 0), COALESCE(SUM(output_tokens), 0) FROM calls").fetchone()
    return row[0], row[1]


def _reason(detail: str) -> str:
    """trace 는 긴 detail 을 잘라 저장하므로, JSON 이 깨졌으면 reason 뒤의 글자를 그대로 쓴다."""
    try:
        return json.loads(detail)["reason"]
    except ValueError:
        return detail.split('"reason": "', 1)[-1]


class CountingPost:
    """CLOVA 호출을 세는 post. 사례마다 하나씩 만들어 RunContext.post 로 넘긴다."""

    def __init__(self):
        self.calls = 0
        self._lock = threading.Lock()

    def __call__(self, url, **kwargs):
        with self._lock:
            self.calls += 1
        return httpx.post(url, **kwargs)


def rate_limited(path: Path) -> int:
    """측정 중 받은 429 수. 동시 한도를 너무 높였는지 볼 때 쓴다."""
    if not path.exists():
        return 0
    with sqlite3.connect(path) as conn:
        return conn.execute("SELECT COUNT(*) FROM calls WHERE http_status = 429").fetchone()[0]


def run(runs: int, only: list[str] | None, workers: int = 4) -> dict:
    from Harness.spec import RunContext
    from Harness.tests.fakes import NOW, make_snapshot

    out = OUT_ROOT / dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    out.mkdir(parents=True, exist_ok=True)
    clova_usage_log.LOG_PATH = out / "clova_usage.db"
    trace.TRACE_PATH = out / "harness_trace.db"

    cases = {name: fn for name, fn in _cases().items() if not only or name in only}
    results: dict[str, list[dict]] = {name: [] for name in cases}
    cache.clear()
    cache.get = lambda key: None  # 측정 중에는 캐시를 쓰지 않는다
    cache.CACHE_PATH = None  # 파일 캐시도 (측정 결과가 실제 캐시 파일에 쌓이지 않게)

    def one(n: int, name: str) -> None:
        post = CountingPost()
        ctx = RunContext(snapshot=make_snapshot(), now=NOW, post=post)
        started = time.perf_counter()
        try:
            result = cases[name](ctx)
            source = getattr(result, "source", None) or "NONE"
            error = None
        except Exception as exc:  # 측정은 끝까지 간다
            source, error = "ERROR", repr(exc)
        steps = trace.steps_of(ctx.run_id)
        rejected = [_reason(s["detail"]) for s in steps
                    if s["kind"] == "submit" and s["detail"] and '"accepted": false' in s["detail"]]
        row = {"run": n + 1, "source": source, "seconds": round(time.perf_counter() - started, 1),
               "calls": post.calls, "rejected": rejected, "error": error, "run_id": ctx.run_id}
        results[name].append(row)
        print(f"[{n + 1}/{runs}] {name}: {source} ({row['seconds']}초, 호출 {row['calls']}번)", flush=True)

    started_all = time.perf_counter()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for future in [pool.submit(one, n, name) for n in range(runs) for name in cases]:
            future.result()
    print(f"\n전체 {round(time.perf_counter() - started_all)}초 (사례 {workers}개 동시, CLOVA 동시 호출 {limiter.MAX_CONCURRENT}개), "
          f"429 {rate_limited(clova_usage_log.LOG_PATH)}번", flush=True)

    summary = {}
    for name, rows in results.items():
        sources = Counter(r["source"] for r in rows)
        reasons = Counter(reason.split("(")[0].split(":")[0].strip()[:40] for r in rows for reason in r["rejected"])
        summary[name] = {
            "agent": sources.get("AGENT", 0), "fallback": sources.get("FALLBACK", 0),
            "none": sources.get("NONE", 0) + sources.get("ERROR", 0), "runs": len(rows),
            "avg_calls": round(sum(r["calls"] for r in rows) / len(rows), 1),
            "avg_seconds": round(sum(r["seconds"] for r in rows) / len(rows), 1),
            "top_rejections": reasons.most_common(3),
        }
    tokens_in, tokens_out = _tokens(clova_usage_log.LOG_PATH)
    won = tokens_in * settings.clova_price_input_per_1k / 1000 + tokens_out * settings.clova_price_output_per_1k / 1000
    report = {"at": dt.datetime.now().isoformat(timespec="seconds"), "runs": runs, "summary": summary,
              "tokens": [tokens_in, tokens_out], "won": round(won), "detail": results}
    (out / "result.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"\n{'사례':<16}{'에이전트':>8}{'물러남':>6}{'없음':>5}{'평균 호출':>9}{'평균 초':>8}  자주 걸린 거절")
    for name, s in summary.items():
        print(f"{name:<16}{s['agent']:>5}/{s['runs']}{s['fallback']:>6}{s['none']:>5}{s['avg_calls']:>9}{s['avg_seconds']:>8}  {s['top_rejections']}")
    print(f"\n토큰 입력 {tokens_in:,} / 출력 {tokens_out:,}, 약 {round(won)}원 (.env 단가 기준). 기록: {out}")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="실제 CLOVA 로 에이전트 성공률 측정")
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--only", default="", help="쉼표로 구분한 사례 이름")
    parser.add_argument("--workers", type=int, default=4, help="동시에 돌리는 사례 수 (1 이면 하나씩)")
    parser.add_argument("--concurrency", type=int, default=2, help="CLOVA 동시 호출 한도. 4 는 429 가 많이 났다 (2026-11-15)")
    args = parser.parse_args()
    if not settings.clova_studio_api_key:
        raise SystemExit("server/.env 에 CLOVA_STUDIO_API_KEY 가 없어요")
    limiter.set_max_concurrent(args.concurrency)
    run(args.runs, [name for name in args.only.split(",") if name] or None, args.workers)


if __name__ == "__main__":
    main()
