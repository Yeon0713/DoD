"""감사 기록 (voice.db docs, 종류 audit, 계획 10-1). 한 줄 = 한 결과물의 2차 감사 한 회차.

  {id: au_<가게>_<번호>, store_id, job, agent, ref, run_id, round, status: pass | fail | unchecked,
   criterion, reason, quotes, calls, ms, final, hold, at}
round 0 이 첫 감사, 1·2 가 되돌림 뒤 감사. final 은 그 결과물의 마지막 회차. hold 는 끝내 불합격해 사장님께 묻게 된 건.
1차 코드 거절은 남기지 않는다 (실행 기록 trace 에 있다).
"""

import datetime as dt
from collections import Counter, defaultdict

from voice import clock, repo
from voice.clock import parse

KIND = "audit"


def record_trail(store_id: str, job: str, agent: str, ref: str, audit: dict | None, run_id: str | None = None) -> list[dict]:
    """Proposal.audit 의 회차들(trail)을 남긴다. 감사 자리가 없거나 회차가 없으면 아무것도 남기지 않는다."""
    trail = (audit or {}).get("trail") or []
    rows = []
    for n, step in enumerate(trail):
        aid = f"au_{store_id}_{repo.next_number(f'audit:{store_id}'):04d}"
        rows.append(repo.put(KIND, aid, store_id, {
            "id": aid, "store_id": store_id, "job": job, "agent": agent, "ref": ref, "run_id": run_id,
            "round": step.get("round", n), "status": step["status"], "criterion": step.get("criterion"),
            "reason": step.get("reason"), "quotes": step.get("quotes") or [], "calls": step.get("calls", 0),
            "ms": step.get("ms", 0), "final": n == len(trail) - 1, "hold": False, "at": clock.iso(clock.now())}))
    return rows


def record_run(store_id: str, job: str, ref: str, proposal, run_id: str) -> list[dict]:
    """담당 입구에서: 이번 실행이 새로 만든 결과(캐시에서 되살린 것이 아님)의 감사 회차를 남긴다."""
    if proposal is None or proposal.audit is None or proposal.run_id != run_id:
        return []
    return record_trail(store_id, job, proposal.agent, ref, proposal.audit, run_id)


def mark_hold(store_id: str, ref: str) -> None:
    """그 결과물의 마지막 회차에 보류 표시 (대시보드 보류 수)."""
    with repo.lock():
        for row in repo.all_of(KIND, store_id):
            if row["ref"] == ref and row["final"] and not row["hold"]:
                repo.put(KIND, row["id"], store_id, {**row, "hold": True})


def rows_of(store_id: str, day: dt.date | None = None) -> list[dict]:
    return [r for r in repo.all_of(KIND, store_id) if day is None or parse(r["at"]).date() == day]


def day_summary(store_id: str, day: dt.date) -> dict:
    """그날 기록과 업무별 요약 (계획 12장)."""
    rows = rows_of(store_id, day)
    per_job: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        per_job[row["job"]].append(row)
    jobs = []
    for job, found in per_job.items():
        finals = [r for r in found if r["final"]]
        ms = [r["ms"] for r in found]
        jobs.append({
            "job": job, "results": len(finals),
            "first_pass": sum(1 for r in finals if r["status"] == "pass" and r["round"] == 0),
            "pass_after_return": sum(1 for r in finals if r["status"] == "pass" and r["round"] > 0),
            "final_fail": sum(1 for r in finals if r["status"] == "fail"),
            "hold": sum(1 for r in finals if r["hold"]),
            "unchecked": sum(1 for r in finals if r["status"] == "unchecked"),
            "fail_by_criterion": dict(Counter(r["criterion"] for r in found if r["status"] == "fail")),
            "avg_ms": round(sum(ms) / len(ms)) if ms else 0, "max_ms": max(ms, default=0),
            "calls": sum(r["calls"] for r in found),
        })
    return {"store_id": store_id, "day": day.isoformat(), "jobs": jobs, "rows": rows}
