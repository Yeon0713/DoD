"""알바생 할 일 제안 (2026-11-20 에이전트 조직 개편 1단계, donna-voice/docs/agent-org-plan.md).

사원(에이전트·규칙)은 알바생 할 일을 바로 넣지 않고 제안으로 남긴다. 사장님이 승인하면 apply 가 넣는다.
사원이 제안한 할 일을 실제로 넣는 곳은 여기 하나다 (사장님이 말로 시킨 일, 매뉴얼, 이벤트 카드는 각자 넣는다).

저장: repo 종류 proposal, id pr_<번호>
  {id, store_id, dept, by, payload, reason, link, state, task_id, created_at, decided_at, decided_by}
  dept     customer | quality | marketing
  by       넣자고 한 사원. negative_review (아쉬운 리뷰 교정)
  payload  할 일 모양 {title, detail, phase, repeat, days, must_confirm, urgent}
  reason   왜 넣자고 했나 {type, ...} (리뷰면 review_id)
  link     할 일 source 에 그대로 붙일 것 (리뷰 교정은 alert_id 등. jobs/review_loop.on_staff_confirm 이 읽는다)
상태: proposed → asked → applied | declined
"""

from voice import clock, repo, staff
from voice.clock import iso

KIND = "proposal"
ORIGIN = {"negative_review": "review"}  # 할 일 표의 origin (화면 문구와 "시킨 거 다 했대?"가 본다)


def create(store_id: str, *, dept: str, by: str, payload: dict, reason: dict, link: dict | None = None,
           state: str = "proposed") -> dict:
    pid = f"pr_{repo.next_number(f'proposal:{store_id}'):04d}"
    return repo.put(KIND, pid, store_id, {
        "id": pid, "store_id": store_id, "dept": dept, "by": by, "payload": payload, "reason": reason, "link": link or {},
        "state": state, "task_id": None, "created_at": iso(clock.now()), "decided_at": None, "decided_by": None,
    })


def get(pid: str) -> dict | None:
    return repo.get(KIND, pid)


def apply(pid: str, trigger: str) -> dict:
    """승인한 제안을 알바생 할 일로 넣는다. 이미 넣었으면 그 할 일을 돌려준다 (두 번 넣지 않는다)."""
    with repo._lock:
        found = get(pid)
        if found["state"] == "applied":
            return next(t for t in staff.store_tasks(found["store_id"]) if t["id"] == found["task_id"])
        p = found["payload"]
        task = staff.add_task(
            found["store_id"], p["title"], p["phase"], repeat=p.get("repeat", "today"), must_confirm=p.get("must_confirm", False),
            urgent=p.get("urgent", False), detail=p.get("detail"), days=p.get("days", 1), origin=ORIGIN[found["by"]],
            source={**found["link"], "by": found["by"], "dept": found["dept"], "proposal_id": pid, "reason": found["reason"]},
        )
        repo.put(KIND, pid, found["store_id"], {**found, "state": "applied", "task_id": task["id"],
                                               "decided_at": iso(clock.now()), "decided_by": trigger})
    return task


def decline(pid: str, trigger: str) -> None:
    with repo._lock:
        found = get(pid)
        if found and found["state"] not in ("applied", "declined"):
            repo.put(KIND, pid, found["store_id"], {**found, "state": "declined", "decided_at": iso(clock.now()), "decided_by": trigger})
