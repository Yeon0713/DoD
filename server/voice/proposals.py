"""알바생 할 일 제안 (2026-11-20 에이전트 조직 개편, donna-voice/docs/agent-org-plan.md 1·2단계).

사원(에이전트·규칙)은 알바생 할 일을 바로 넣지 않고 제안으로 남긴다. 사장님이 승인하면 apply 가 넣는다.
사원이 제안한 할 일을 실제로 넣는 곳은 여기 하나다 (사장님이 말로 시킨 일, 매뉴얼, 이벤트 카드는 각자 넣는다).

저장: repo 종류 proposal, id pr_<가게>_<번호> (repo 키는 가게를 가리지 않는다)
  {id, store_id, dept, by, payload, reason, link, state, same_as, merged, task_id, created_at, decided_at, decided_by}
  dept     customer | quality | marketing
  by       넣자고 한 사원. negative_review (아쉬운 리뷰 교정) | manual_coach (반복 → 매뉴얼)
  payload  할 일 모양 {title, detail, phase, repeat, days, must_confirm, urgent}
  reason   왜 넣자고 했나 {type, ...} (리뷰면 review_id, 반복이면 task_id·count)
  link     할 일 source 에 그대로 붙일 것 (리뷰 교정은 alert_id 등. jobs/review_loop.on_staff_confirm 이 읽는다)
상태: proposed → asked → applied | declined,  같은 일이 이미 있으면 merged (same_as = 그 할 일·제안 id)

같은 일 찾기 (2단계): 같은 출처(같은 리뷰)나 거의 같은 글이면 바로 묶는다. 아니면 바이그램 겹침(similar.dice)으로 후보를 고르고,
후보가 있을 때만 좁은 LLM 질문(agents/same_task)에 묻는다. 묶이면 새로 넣지 않고 기존 할 일 source.merged 에 적는다.
기존이 일반이고 새 것이 긴급이면 묶지 않는다 (긴급이 사라지지 않게).
반복 → 매뉴얼 (2단계, 매뉴얼 코칭 사원): 한 할 일이 7일 안에 3번(처음 + 묶인 것) 나오면 매일 할 일로 올리자고 제안한다.
"""

import datetime as dt

from voice import clock, repo, staff, staff_db
from voice.clock import iso, parse
from voice.similar import dice

KIND = "proposal"
# 할 일 표의 origin (화면 문구와 "시킨 거 다 했대?"가 본다)
ORIGIN = {"negative_review": "review", "manual_coach": "manual", "field_variable": "field_variable"}
LIVE = ("proposed", "asked")
SAME_SCORE = 0.35  # 이 이상 겹치는 할 일만 LLM 에 묻는다 (시작값. 시험으로 맞춘다)
SAME_TEXT = 0.9  # 이 이상이면 글이 거의 같다. LLM 없이 묶는다
LOOK_BACK = dt.timedelta(days=7)
REPEAT = 3
DEPT_ORDER = ("customer", "quality", "marketing")  # 사장님께 말할 부서 순서 (2026-11-21 팀장 없앰, agent-structure.md 5장)


def urgent(found: dict) -> bool:
    """긴급: 사원이 긴급이라 했거나, 현장 변수의 '오늘 손님이 바로 겪는 일'(today_impact)."""
    return bool(found["payload"].get("urgent") or found["payload"].get("today_impact"))


def _text(payload_or_task: dict) -> str:
    return f"{payload_or_task['title']} {payload_or_task.get('detail') or ''}".strip()


def create(store_id: str, *, dept: str, by: str, payload: dict, reason: dict, link: dict | None = None,
           state: str = "proposed", dedupe: bool = True, ask_on: str | None = None) -> dict:
    """ask_on: 아침 브리핑에서 물을 날 (YYYY-MM-DD). 없으면 부르는 쪽이 그 자리에서 묻는다 (영업 중 아쉬운 리뷰)."""
    pid = f"pr_{store_id}_{repo.next_number(f'proposal:{store_id}'):04d}"  # repo 키는 가게를 가리지 않으므로 가게 id 를 넣는다
    record = {
        "id": pid, "store_id": store_id, "dept": dept, "by": by, "payload": payload, "reason": reason, "link": link or {},
        "state": state, "same_as": None, "merged": [], "task_id": None, "ask_on": ask_on, "created_at": iso(clock.now()),
        "decided_at": None, "decided_by": None,
    }
    same = _find_same(store_id, record) if dedupe else None
    if same is not None:
        record = {**record, "state": "merged", "same_as": same["id"]}
        _note_merged(same, record)
    return repo.put(KIND, pid, store_id, record)


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
            urgent=urgent(found), detail=p.get("detail"), days=p.get("days", 1), origin=ORIGIN[found["by"]],
            source={**found["link"], "by": found["by"], "dept": found["dept"], "proposal_id": pid, "reason": found["reason"]},
        )
        repo.put(KIND, pid, found["store_id"], {**found, "state": "applied", "task_id": task["id"],
                                               "decided_at": iso(clock.now()), "decided_by": trigger})
        if found["by"] == "manual_coach":  # 묶음당 한 번만 올린다
            root = staff_db.task(found["reason"]["task_id"])
            if root:
                staff_db.update_task_source(root["task_id"], {**(root["source"] or {}), "promoted_at": iso(clock.now())})
    return task


def decline(pid: str, trigger: str) -> None:
    with repo._lock:
        found = get(pid)
        if found and found["state"] in LIVE:
            repo.put(KIND, pid, found["store_id"], {**found, "state": "declined", "decided_at": iso(clock.now()), "decided_by": trigger})


# ── 브리핑에서 묻기 (3단계) ──


def for_review(store_id: str, review_id: str) -> dict | None:
    """그 리뷰에서 나온 제안 (같은 리뷰로 다시 만들지 않게)."""
    return next((p for p in repo.all_of(KIND, store_id) if p["reason"].get("review_id") == review_id), None)


def for_briefing(store_id: str, day: str, *, include_asked: bool = False) -> list[dict]:
    """그날 물을 제안: 아직 묻지 않은 것 (include_asked 면 물었는데 대답이 없는 것도). 긴급 → 부서 순서 → 들어온 순서."""
    states = LIVE if include_asked else ("proposed",)
    found = [p for p in repo.all_of(KIND, store_id) if p.get("ask_on") and p["ask_on"] <= day and p["state"] in states]
    return sorted(found, key=lambda p: (not urgent(p), DEPT_ORDER.index(p["dept"]), p["created_at"]))


def mark_asked(pids: list[str]) -> None:
    with repo._lock:
        for pid in pids:
            found = get(pid)
            if found and found["state"] == "proposed":
                repo.put(KIND, pid, found["store_id"], {**found, "state": "asked"})


def carry(pid: str, ask_on: str) -> None:
    """대답이 없던 제안을 그날(ask_on) 아침 브리핑으로 넘긴다 (자동 답글 뒤 할 일, 2026-11-20 결정)."""
    with repo._lock:
        found = get(pid)
        if found and found["state"] in LIVE:
            repo.put(KIND, pid, found["store_id"], {**found, "state": "proposed", "ask_on": ask_on})


def expire(store_id: str, today: str) -> int:
    """물을 날이 지난 제안을 버린다 (브리핑을 듣지 않으면 넣지 않는다, 2026-11-20 결정)."""
    gone = 0
    with repo._lock:
        for p in repo.all_of(KIND, store_id):
            if p.get("ask_on") and p["ask_on"] < today and p["state"] in LIVE:
                repo.put(KIND, p["id"], store_id, {**p, "state": "expired", "decided_by": "expired"})
                gone += 1
    return gone


# ── 같은 일 찾기 ──


def _candidates(store_id: str, record: dict) -> list[dict]:
    """지금 보이는(또는 7일 안에 넣은) 할 일과 아직 정하지 않은 제안.
    영업 중 알림에서 물은 제안(asked, 물을 날 없음)은 알림이 2시간 지나면 끝난 것으로 보고 뺀다 (예전에 남은 것)."""
    from voice.jobs.review_loop import LOOK_BACK as ALERT_LOOK_BACK

    now = clock.now()
    found = [{"id": t["id"], "kind": "task", "text": _text(t), "urgent": t["urgent"], "source": t["source"] or {}}
             for t in staff.store_tasks(store_id)
             if not t["canceled"] and (t["repeat"] == "daily" or now - parse(t["created_at"]) <= LOOK_BACK)]
    found += [{"id": p["id"], "kind": "proposal", "text": _text(p["payload"]), "urgent": urgent(p),
               "source": p["link"]}
              for p in repo.all_of(KIND, store_id) if p["state"] in LIVE and p["id"] != record["id"]
              and not (p["state"] == "asked" and not p.get("ask_on") and now - parse(p["created_at"]) > ALERT_LOOK_BACK)]
    return found


def _same_source(a: dict, b: dict) -> bool:
    return bool(a.get("review_id")) and a.get("review_id") == b.get("review_id")


def _find_same(store_id: str, record: dict) -> dict | None:
    candidates = _candidates(store_id, record)
    if urgent(record):  # 긴급은 일반 할 일과 묶지 않는다 (현장 변수 today_impact 도 긴급)
        candidates = [c for c in candidates if c["urgent"]]
    same = next((c for c in candidates if _same_source(c["source"], record["link"])), None)
    if same:
        return same
    text = _text(record["payload"])
    scored = sorted(((dice(text, c["text"]), c) for c in candidates), key=lambda sc: -sc[0])
    if scored and scored[0][0] >= SAME_TEXT:
        return scored[0][1]
    close = [c for score, c in scored if score >= SAME_SCORE]
    if not close:
        return None
    from voice.agents import same_task
    from voice.context import load

    chosen = same_task.judge(load(store_id), text, [{"id": c["id"], "text": c["text"]} for c in close])
    return next((c for c in close if c["id"] == chosen), None)


def _note_merged(same: dict, record: dict) -> None:
    entry = {"proposal_id": record["id"], "by": record["by"], "reason": record["reason"], "at": record["created_at"]}
    if same["kind"] == "task":
        row = staff_db.task(same["id"])
        source = row["source"] or {}
        staff_db.update_task_source(same["id"], {**source, "merged": [*(source.get("merged") or []), entry]})
    else:
        other = get(same["id"])
        repo.put(KIND, other["id"], other["store_id"], {**other, "merged": [*other.get("merged", []), entry]})


# ── 반복 → 매뉴얼 (매뉴얼 코칭 사원) ──


def promote_repeats(store_id: str) -> list[dict]:
    """7일 안에 3번 나온 할 일마다 '매일 할 일로 올릴까요?' 제안을 만든다. 할 일 하나에 한 번만."""
    now = clock.now()
    asked_for = {p["reason"].get("task_id") for p in repo.all_of(KIND, store_id) if p["by"] == "manual_coach"}
    made = []
    for task in staff.store_tasks(store_id):
        source = task["source"] or {}
        if task["canceled"] or task["repeat"] == "daily" or not source.get("proposal_id"):
            continue  # 제안에서 나온 오늘만 일만 (사장님이 말로 시킨 일, 매뉴얼은 빼고)
        if source.get("promoted_at") or task["id"] in asked_for or now - parse(task["created_at"]) > LOOK_BACK:
            continue
        merged = [m for m in source.get("merged") or [] if now - parse(m["at"]) <= LOOK_BACK]
        count = 1 + len(merged)
        if count < REPEAT:
            continue
        made.append(_propose_manual(store_id, task, merged, count))
    return made


def _propose_manual(store_id: str, task: dict, merged: list[dict], count: int) -> dict:
    from voice.agents import manual_line
    from voice.context import load

    items = [_text(task)] + [_text(get(m["proposal_id"])["payload"]) for m in merged if get(m["proposal_id"])]
    manual = [t["title"] for t in staff.store_tasks(store_id) if t["repeat"] == "daily" and not t["canceled"]]
    line = manual_line.write(load(store_id), items, manual) or {"title": task["title"], "detail": task.get("detail")}
    return create(
        store_id, dept="quality", by="manual_coach", dedupe=False, ask_on=clock.now().date().isoformat(),
        payload={"title": line["title"], "detail": line["detail"], "phase": task["phase"], "repeat": "daily", "must_confirm": False},
        reason={"type": "repeat", "task_id": task["id"], "count": count},
    )
