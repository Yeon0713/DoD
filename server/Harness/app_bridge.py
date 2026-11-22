"""기존 서버(app/) 흐름에 에이전트 하네스를 잇는 곳. 스위치(settings.agent_harness_enabled)로 켜고 끈다.

꺼져 있으면(기본) 아무것도 하지 않고, 기존 단일 호출(write_drafts, menu_candidates, ment.suggest)이 그대로 돈다.
켜져 있으면 가게 계산(store_snapshot_cache)이 끝날 때마다 아래를 뒤에서 돌린다. 화면 요청은 기다리지 않는다 (설계 원칙 3).
  1. 답글·재주문 인사 초안   reply_agent    → snapshot.draft_texts 를 채운다 (기존 write_drafts 대신)
  2. 반복 불만 원인 분석     complaint_agent → 결과는 개발자 대시보드에서 본다 (앱 화면 연결은 아직)
  3. 메뉴판·포스터 (7일 안)  campaign_agent → 메뉴판 후보(menu_lookup)와 포스터 멘트(poster_ments)로 쓴다
  4. 앞으로 24시간 안 알림 묶음 중 충돌이 있는 것   supervisor → 받아들인 재작업은 1~3의 결과를 바꾼다
에이전트가 실패하면 각 에이전트의 물러나기(= 기존 단일 호출)가 돈다. 결과는 서버 메모리에만 있다.

app/ 에서 Harness 를 부를 때 서로 import 가 얽히지 않게 에이전트는 함수 안에서 import 한다.
"""

import datetime as dt
import logging
import threading
from concurrent.futures import ThreadPoolExecutor

from app.core.config import settings
from app.core.seoul_time import now_seoul
from app.menu_board.menu_candidates import EMPTY, MenuCandidates
from Harness.spec import Proposal, RunContext

logger = logging.getLogger(__name__)

CAMPAIGN_DAYS = 7  # 메뉴판·포스터는 오늘부터 이만큼 안의 할 일만 (호출 수를 줄인다)
SUPERVISOR_HOURS = 24

_lock = threading.Lock()
_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="agent-harness")  # CLOVA 동시 한도는 limiter 가 따로 지킨다
_proposals: dict[str, dict[str, Proposal]] = {}  # 가게 → 할 일 id → 제안
_menu_by_kind: dict[str, dict[str, MenuCandidates]] = {}  # 가게 → 메뉴판 세부 종류 → 후보
_batches: dict[str, list[dict]] = {}  # 가게 → supervisor 가 본 묶음
_jobs: dict[str, dict] = {}  # 가게 → 지금 작업 진행 (대시보드)


def enabled() -> bool:
    return settings.agent_harness_enabled


def set_enabled(value: bool) -> dict:
    """스위치를 바꾼다. 보관한 가게 계산을 지워 다음 요청부터 바뀐 방식으로 다시 계산한다."""
    from app.data_pipeline import store_snapshot_cache

    settings.agent_harness_enabled = value
    with _lock:
        _proposals.clear()
        _menu_by_kind.clear()
        _batches.clear()
    store_snapshot_cache.clear_snapshots()
    return {"AGENT_HARNESS_ENABLED": value}


# ── 가게 계산이 쓰는 것 ──


def known_drafts(store_id: str, plan_ids: list[str]) -> dict[str, str]:
    """에이전트가 이미 써 둔 초안 (새로 계산한 결과에 바로 채운다)."""
    with _lock:
        found = _proposals.get(store_id, {})
        return {pid: found[pid].content["text"] for pid in plan_ids if pid in found and "text" in found[pid].content}


def menu_lookup(store: dict, menus: list, kind: str) -> MenuCandidates:
    """메뉴판 배치안의 LLM 후보 자리에 쓴다 (menu_candidates 와 같은 모양). 아직 없으면 빈 후보 → 데이터 점수만."""
    with _lock:
        return _menu_by_kind.get(store["store_id"], {}).get(kind, EMPTY)


def poster_ments(store_id: str, plan_id: str) -> list[dict] | None:
    """포스터 할 일의 에이전트 멘트. 없으면 None (부르는 쪽이 기존 ment.suggest 를 쓴다).
    물러나기(FALLBACK) 결과는 기존 ment.suggest 의 문구라 여기서 돌려주지 않는다 (출처를 'AGENT'로 잘못 보이지 않게)."""
    with _lock:
        proposal = _proposals.get(store_id, {}).get(plan_id)
    ments = proposal.content.get("ments") if proposal and proposal.source == "AGENT" else None
    return ments or None


def start(snapshot, reply_plan_ids: list[str]) -> bool:
    """가게 계산이 끝난 뒤 부른다. 스위치가 꺼져 있거나 같은 가게 작업이 이미 돌고 있으면 맡기지 않는다."""
    if not enabled() or snapshot.plan is None:
        return False
    with _lock:
        job = _jobs.get(snapshot.store_id)
        if job and job["state"] in ("queued", "running"):
            return False
        _jobs[snapshot.store_id] = {"state": "queued", "queued_at": now_seoul().isoformat(timespec="seconds"), "done": 0, "total": 0,
                                    "current": None}
    _executor.submit(_run_safely, snapshot, reply_plan_ids)
    return True


def _run_safely(snapshot, reply_plan_ids: list[str]) -> None:
    try:
        run_all(snapshot, reply_plan_ids)
    except Exception:  # 에이전트가 모두 실패해도 화면은 기존 결과로 동작한다
        logger.exception("%s 가게 에이전트 실행 실패", snapshot.store_id)
        _update(snapshot.store_id, state="failed")


def _update(store_id: str, **fields) -> None:
    with _lock:
        _jobs.setdefault(store_id, {}).update(fields)


def _todo(snapshot, reply_plan_ids: list[str]) -> list:
    """에이전트에 맡길 할 일 (이미 제안이 있는 것은 빼고): 답글·재주문 인사, 반복 불만, 7일 안 메뉴판·포스터."""
    today = snapshot.computed_at.date()
    with _lock:
        done = set(_proposals.get(snapshot.store_id, {}))
    items = []
    for item in snapshot.plan.plan_items:
        if item.plan_id in done:
            continue
        if item.plan_id in reply_plan_ids or item.task_type == "REVIEW_FIX":
            items.append(item)
        elif item.task_type in ("MENU_ORDER", "POSTER"):
            day = dt.date.fromisoformat(item.plan_id.split(":")[-1])
            if today <= day <= today + dt.timedelta(days=CAMPAIGN_DAYS):
                items.append(item)
    return items


def run_all(snapshot, reply_plan_ids: list[str]) -> None:
    """일꾼 에이전트 → supervisor 순서로 돌리고 결과를 기억한다 (테스트는 이 함수를 바로 부른다)."""
    from Harness.agents import campaign_agent, complaint_agent, reply_agent

    store_id = snapshot.store_id
    items = _todo(snapshot, reply_plan_ids)
    _update(store_id, state="running", started_at=now_seoul().isoformat(timespec="seconds"), total=len(items), done=0)
    for number, item in enumerate(items, 1):
        _update(store_id, current=f"{item.task_type} {item.plan_id}")
        ctx = RunContext(snapshot=snapshot, now=snapshot.computed_at)
        try:  # 결과를 기억하는 데까지 잡는다: 할 일 하나가 실패해도 남은 할 일과 supervisor 는 계속 돈다 (H9)
            if item.task_type in ("REVISIT_REPLY", "REORDER_NUDGE"):
                proposal = reply_agent.draft(item, ctx)
            elif item.task_type == "REVIEW_FIX":
                proposal = complaint_agent.diagnose(item, ctx)
            else:
                proposal = campaign_agent.plan_campaign(item, ctx)
            if proposal is not None:
                _remember(snapshot, item, proposal)
        except Exception:
            logger.exception("%s 에이전트 실패: %s", store_id, item.plan_id)
        _update(store_id, done=number)

    _update(store_id, current="supervisor")
    _coordinate(snapshot)
    _update(store_id, state="done", current=None, finished_at=now_seoul().isoformat(timespec="seconds"))


def _remember(snapshot, item, proposal: Proposal) -> None:
    from Harness.agents import campaign_agent

    if not isinstance(proposal, Proposal):  # 모양이 틀린 값을 기억하면 대시보드(status)까지 깨진다. 기억하기 전에 실패시킨다 (H1)
        raise TypeError(f"{item.plan_id} 제안이 Proposal 이 아니에요 ({type(proposal).__name__})")
    store_id = snapshot.store_id
    with _lock:
        _proposals.setdefault(store_id, {})[item.plan_id] = proposal
    if "text" in proposal.content:
        snapshot.draft_texts[item.plan_id] = proposal.content["text"]  # 앱이 다시 불러오면 보인다
    if item.task_type == "MENU_ORDER" and proposal.content.get("menu_ids"):
        kind = campaign_agent.task_for_plan_item(item, RunContext(snapshot=snapshot, now=snapshot.computed_at)).get("kind")
        if kind:
            with _lock:
                _menu_by_kind.setdefault(store_id, {})[kind] = MenuCandidates(
                    tuple(proposal.content["menu_ids"]), str(proposal.content.get("reason") or ""))


def _coordinate(snapshot) -> None:
    from Harness import supervisor

    store_id = snapshot.store_id
    until = snapshot.computed_at + dt.timedelta(hours=SUPERVISOR_HOURS)
    seen = []
    for batch in snapshot.plan.batches:
        if not snapshot.computed_at <= batch.slot_at <= until:
            continue
        with _lock:
            proposals = dict(_proposals.get(store_id, {}))
        in_batch = {e.plan_id: proposals[e.plan_id] for e in batch.entries if e.plan_id in proposals}
        try:  # 결과를 기억하는 데까지 잡는다: 묶음 하나가 실패해도 남은 묶음과 _batches 는 계속 처리한다
            result = supervisor.coordinate_batch(batch, in_batch, RunContext(snapshot=snapshot, now=snapshot.computed_at))
            if result.source == "NONE":
                continue
            item_by_id = {i.plan_id: i for i in snapshot.plan.plan_items}
            for plan_id, proposal in result.proposals.items():
                if proposals.get(plan_id) is not proposal and plan_id in item_by_id:
                    _remember(snapshot, item_by_id[plan_id], proposal)
            seen.append({
                "slot_at": batch.slot_at.isoformat(timespec="minutes"), "source": result.source, "run_id": result.run_id,
                "headline": result.headline, "conflicts": [c.describe() for c in result.conflicts], "item_notes": result.item_notes,
            })
        except Exception:
            logger.exception("%s supervisor 실패: %s", store_id, batch.slot_at)
            continue
    with _lock:
        _batches[store_id] = seen


# ── 개발자 대시보드 ──


def status() -> dict:
    """스위치, 가게별 작업 진행, 가게별 제안 수(에이전트/물러나기), supervisor 가 본 묶음."""
    with _lock:
        stores = sorted(set(_jobs) | set(_proposals))
        per_store = []
        for store_id in stores:
            proposals = _proposals.get(store_id, {})
            per_store.append({
                "store_id": store_id, "job": dict(_jobs.get(store_id, {})),
                "proposals": [{"plan_id": pid, "agent": p.agent, "source": p.source, "run_id": p.run_id, "notes": p.notes,
                               "summary": _summary(p)} for pid, p in proposals.items()],
                "batches": list(_batches.get(store_id, [])),
            })
    return {"enabled": enabled(), "stores": per_store}


def _summary(proposal: Proposal) -> str:
    content = proposal.content
    if "text" in content:
        return str(content["text"])
    if "hypotheses" in content:
        return " / ".join(h["text"] for h in content["hypotheses"]) or str(content.get("reason_line", ""))
    heads = " / ".join(str(m.get("headline", "")).replace("\n", " ") for m in content.get("ments") or [])
    return f"메뉴 {', '.join(content.get('menu_ids') or []) or '없음'} | 포스터 {heads or '없음'}"


def forget_all() -> None:
    """테스트용."""
    with _lock:
        _proposals.clear()
        _menu_by_kind.clear()
        _batches.clear()
        _jobs.clear()
