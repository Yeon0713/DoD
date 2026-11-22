"""Supervisor: 알림 묶음 조율자.

무엇을 언제 어떤 순서로 할지는 계획 엔진이 정한다. supervisor 는 같은 알림 묶음 안에서 일꾼 에이전트들의 결과가
서로 어긋나지 않게 조율만 한다.

1. 충돌 찾기는 코드가 한다 (conflicts.py). 충돌이 없는 묶음은 supervisor 를 부르지 않는다 (CLOVA 추가 호출 0회).
2. 어떻게 풀지는 supervisor 가 정한다. 일꾼에게 줄 지시 한 줄을 쓰고, 재작업 결과를 받을지 정하고, 묶음 첫 줄을 쓴다.
3. 재작업은 일꾼이 한다. 일꾼 AgentSpec 을 도구로 감싸(agent-as-tool) 부르고, 다시 쓴 초안도 일꾼의 검사를 통과해야 한다.
   supervisor 가 글을 직접 고치지는 않는다.

할 수 없는 것: 할 일 더하기·빼기, 시각·우선순위 바꾸기, 글 직접 고치기 (제출에 그런 칸이 있으면 거절).
예산: supervisor 4단계, 할 일당 재작업 1번, 묶음당 재작업 최대 3건. 일꾼 호출도 같은 CallBudget 에서 뺀다.
물러나기: 재작업 없이 충돌 메모만 규칙 문장으로 카드에 붙인다.
"""

import dataclasses
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

from app.core.seoul_time import to_seoul
from app.planner.data_shapes import NotificationBatch, PlanItem
from app.planner.rule_complaint_fix import COMPLAINT_NAMES
from Harness import runner
from Harness.agents import campaign_agent, complaint_agent, reply_agent
from Harness.conflicts import KIND_NAMES, Conflict, find_conflicts, open_risks, plan_ids_of
from Harness.grounding import Evidence, ungrounded_numbers
from Harness.spec import AgentSpec, Budget, CallBudget, Proposal, RunContext, Tool
from Harness.store_tools import day_label
from Harness.tools import array, load_prompt, obj, string

MAX_REVISIONS = 3  # 묶음당 재작업
SHARED_CALLS = 30  # supervisor 와 그 아래 일꾼 재작업이 함께 쓰는 CLOVA 호출 수
MAX_HEADLINE = 40
MAX_NOTE = 80
SUBMIT_KEYS = {"headline", "item_notes", "accepted"}


@dataclass
class BatchResult:
    plan_ids: list[str]
    proposals: dict[str, Proposal]  # 할 일 id → 최종 제안 (받아들인 재작업은 바뀌어 있다)
    conflicts: list[Conflict]
    headline: str | None = None
    item_notes: dict[str, list[str]] = field(default_factory=dict)
    source: Literal["NONE", "AGENT", "FALLBACK"] = "NONE"  # NONE: 충돌이 없어 supervisor 를 부르지 않음
    run_id: str | None = None


# ── 제안 요약 (supervisor 가 읽는 글) ──


def summarize(proposal: Proposal | None, names: dict[str, str]) -> str:
    if proposal is None:
        return "(초안 없음)"
    content = proposal.content
    if "text" in content:
        return str(content["text"])
    if "hypotheses" in content:
        texts = [h["text"] for h in content["hypotheses"]]
        return " / ".join(texts) if texts else str(content.get("reason_line", ""))
    menus = ", ".join(names.get(m, m) for m in content.get("menu_ids") or [])
    heads = " / ".join(str(m.get("headline", "")).replace("\n", " ") for m in content.get("ments") or [])
    return f"메뉴판: {menus or '없음'} | 포스터: {heads or '없음'}"


# ── 일꾼을 도구로 감싸기 ──


def _item(ctx: RunContext, plan_id: str) -> PlanItem | None:
    plan = ctx.snapshot.plan
    return next((i for i in plan.plan_items if i.plan_id == plan_id), None) if plan else None


def agent_tool(name: str, description: str, parameters: dict, task_types: tuple[str, ...],
               call: Callable[[PlanItem, RunContext, dict], Proposal | None], plan_id_of: Callable[[dict, dict], str | None]) -> Tool:
    """일꾼 에이전트를 supervisor 의 도구로 감싼다. 일꾼은 supervisor 실행 아래(parent_run_id)에서 돈다."""

    def func(ctx: RunContext, task: dict, args: dict) -> dict:
        plan_id = plan_id_of(task, args)
        if plan_id is None or plan_id not in task["plan_ids"]:
            return {"error": "이 묶음에 없는 할 일이에요"}
        item = _item(ctx, plan_id)
        if item is None or item.task_type not in task_types:
            return {"error": f"이 도구로 다시 쓸 수 없는 할 일이에요 ({item.task_type if item else '없음'})"}
        if plan_id in task["asked"]:
            return {"error": "이 할 일은 이미 한 번 다시 쓰게 했어요"}
        if len(task["asked"]) >= MAX_REVISIONS:
            return {"error": f"묶음 전체 재작업은 {MAX_REVISIONS}번까지예요"}
        task["asked"].append(plan_id)
        proposal = call(item, ctx.child(), args)
        if proposal is None or proposal.source != "AGENT":
            return {"plan_id": plan_id, "status": "failed", "note": "다시 쓰지 못했어요. 메모로 남겨 주세요"}
        task["revised"][plan_id] = proposal
        return {"plan_id": plan_id, "status": "rewritten", "draft": summarize(proposal, task["menu_names"])}

    return Tool(name, description, parameters, func)


def _plan_id_arg(task: dict, args: dict) -> str | None:
    return str(args.get("plan_id") or "") or None


def _fix_plan_id(task: dict, args: dict) -> str | None:
    """risk_id 로 묶음 안의 반복 불만 할 일을 찾는다."""
    risk_id = str(args.get("risk_id") or "")
    return next((pid for pid in task["plan_ids"] if pid.startswith(f"REVIEW_FIX:{risk_id}:")), None)


ASK_REPLY = agent_tool(
    "ask_reply_agent", "리뷰 응대 에이전트에게 지시 한 줄을 주고 답글·재주문 인사를 다시 쓰게 한다",
    obj({"plan_id": string("다시 쓸 할 일 id"), "note": string("일꾼에게 줄 지시 한 줄")}),
    ("REVISIT_REPLY", "REORDER_NUDGE"),
    lambda item, ctx, args: reply_agent.draft(item, ctx, supervisor_note=str(args.get("note") or "")),
    _plan_id_arg,
)
ASK_COMPLAINT = agent_tool(
    "ask_complaint_agent", "반복 불만 원인 분석 에이전트에게 지시 한 줄을 주고 진단을 다시 하게 한다",
    obj({"risk_id": string("위험 신호 id"), "note": string("일꾼에게 줄 지시 한 줄")}),
    ("REVIEW_FIX",),
    lambda item, ctx, args: complaint_agent.diagnose(item, ctx, supervisor_note=str(args.get("note") or "")),
    _fix_plan_id,
)
ASK_CAMPAIGN = agent_tool(
    "ask_campaign_agent", "상황 마케팅 에이전트에게 지시 한 줄과 뺄 메뉴를 주고 메뉴판·포스터 문구를 다시 정하게 한다",
    obj(
        {"plan_id": string("다시 정할 할 일 id"), "note": string("일꾼에게 줄 지시 한 줄"),
         "exclude_menu_ids": array(string("menu_id"), "빼야 할 메뉴 id")},
        required=["plan_id", "note"],
    ),
    ("MENU_ORDER", "POSTER"),
    lambda item, ctx, args: campaign_agent.plan_campaign(
        item, ctx, exclude_menu_ids=[str(m) for m in args.get("exclude_menu_ids") or []], supervisor_note=str(args.get("note") or ""),
    ),
    _plan_id_arg,
)


def get_proposal(ctx: RunContext, task: dict, args: dict) -> dict:
    plan_id = str(args.get("plan_id") or "")
    if plan_id not in task["plan_ids"]:
        return {"error": "이 묶음에 없는 할 일이에요"}
    current = task["revised"].get(plan_id) or task["proposals"].get(plan_id)
    return {"plan_id": plan_id, "rewritten": plan_id in task["revised"],
            "draft": summarize(current, task["menu_names"]), "content": current.content if current else None}


def get_open_risks(ctx: RunContext, task: dict, args: dict) -> list[dict]:
    return [
        {"risk_id": r.risk_id, "complaint": COMPLAINT_NAMES[r.complaint_type], "reviews": len(r.review_ids),
         "last_review": day_label(to_seoul(r.last_at).date())}
        for r in open_risks(ctx)
    ]


GET_PROPOSAL = Tool("get_proposal", "묶음 안 할 일 하나의 지금 초안", obj({"plan_id": string("할 일 id")}), get_proposal)
GET_OPEN_RISKS = Tool("get_open_risks", "열려 있는 반복 불만 목록", obj({}), get_open_risks)
SUBMIT = Tool(
    "submit_batch",
    "조율 결과를 제출한다",
    obj({
        "headline": string("묶음 맨 위 첫 줄, 40자 안, '~요'로 끝"),
        "item_notes": array(obj({"plan_id": string("할 일 id"), "note": string("카드에 붙일 메모, 80자 안")}), "카드에 붙일 메모"),
        "accepted": array(string("할 일 id"), "다시 쓴 초안 중 받아들일 할 일 id"),
    }),
)


# ── 프롬프트와 검사 ──


def user_message(task: dict, ctx: RunContext) -> str:
    rows = ["[묶음 안 할 일과 지금 초안]"]
    for pid in task["plan_ids"]:
        rows.append(f"- {pid}: {summarize(task['proposals'].get(pid), task['menu_names'])}")
    rows.append("\n[규칙이 찾은 충돌]")
    for number, conflict in enumerate(task["conflicts"], 1):
        rows.append(f"{number}. {conflict.describe()}")
    rows.append("\n충돌마다 다시 쓰게 하거나 item_notes 로 메모를 남긴 뒤 submit_batch 로 내줘.")
    return "\n".join(rows)


def _accepted(args: dict, task: dict) -> list[str]:
    """받아들여 실제로 반영할 재작업. 검사와 finalize 가 같은 거름을 쓴다 (H3).
    다시 쓰게 하지 않은 할 일 id 는 거절하지 않고 뺀다 (실제 CLOVA 가 REVIEW_FIX 를 섞은 일이 있다). id 하나를 글자로 내도 받아 준다."""
    raw = args.get("accepted") or []
    if isinstance(raw, str):
        raw = [raw]
    return [str(a) for a in raw if str(a) in task["revised"]]


def check(args: dict, evidence: Evidence, task: dict, ctx: RunContext, notes: list[str]) -> str | None:
    extra = set(args) - SUBMIT_KEYS
    if extra:
        return f"할 수 없는 일이에요 ({', '.join(sorted(extra))}). 할 일 더하기·빼기, 시각 바꾸기, 글 직접 고치기는 못 해요"
    raw_notes = args.get("item_notes") or []
    if not isinstance(raw_notes, list):
        return "item_notes 는 {plan_id, note} 목록이어야 해요"
    noted = set()
    for raw in raw_notes:
        if not isinstance(raw, dict) or str(raw.get("plan_id")) not in task["plan_ids"]:
            return f"item_notes 의 plan_id 는 이 묶음 안 할 일이어야 해요: {', '.join(task['plan_ids'])}"
        note = str(raw.get("note") or "").strip()
        if not note or len(note) > MAX_NOTE:
            return f'{raw["plan_id"]} 메모 "{note}"({len(note)}자)를 1~{MAX_NOTE}자로 써 주세요'
        noted.add(str(raw["plan_id"]))
    loose = ungrounded_numbers(" ".join(str(r.get("note")) for r in raw_notes), evidence)
    if loose:
        return f"메모에 초안·충돌 목록에 없는 숫자를 썼어요: {', '.join(dict.fromkeys(loose))}. 그 숫자를 빼 주세요"
    if not isinstance(args.get("accepted") or [], (list, str)):
        return "accepted 는 할 일 id 목록이어야 해요"
    # 처리는 받아들인 재작업이나 메모다. 다시 쓰게 하기만 하고 실패했거나 받아들이지 않은 것은 처리가 아니다 (H3)
    handled = set(_accepted(args, task)) | noted
    unhandled = [c for c in task["conflicts"] if not handled & set(c.plan_ids)]
    if unhandled:
        return ("처리하지 않은 충돌이 있어요: " + "; ".join(KIND_NAMES[c.kind] for c in unhandled)
                + ". 다시 쓰기에 실패했거나 받아들이지 않은 할 일은 item_notes 로 메모를 남겨 주세요")
    return None


def usable_headline(headline: str, evidence_text: str) -> str | None:
    """묶음 첫 줄은 화면용 문구라, 형식이 틀리면 거절하지 않고 비운다 (실제 CLOVA 가 '~습니다', '오늘의 알림 모음' 을 낸 일이 있다).
    40자 안, '~요'로 끝남(뒤 문장부호는 허용), 초안·충돌 목록에 없는 숫자 없음."""
    headline = headline.strip()
    if not headline or len(headline) > MAX_HEADLINE or not headline.rstrip(".!~ ").endswith("요"):
        return None
    if ungrounded_numbers(headline, Evidence([evidence_text])):
        return None
    return headline


def finalize(args: dict, task: dict, ctx: RunContext) -> dict:
    accepted = _accepted(args, task)
    notes: dict[str, list[str]] = {}
    for raw in args.get("item_notes") or []:
        notes.setdefault(str(raw["plan_id"]), []).append(str(raw["note"]).strip())
    return {
        "headline": usable_headline(str(args.get("headline") or ""), evidence_text=user_message(task, ctx)),
        "item_notes": notes,
        "accepted": accepted,
        "revised": {pid: task["revised"][pid] for pid in accepted},
    }


def fallback(task: dict, ctx: RunContext) -> dict:
    notes: dict[str, list[str]] = {}
    for conflict in task["conflicts"]:
        for pid, note in conflict.rule_notes.items():
            notes.setdefault(pid, []).append(note)
    return {"headline": None, "item_notes": notes, "accepted": [], "revised": {}}


SPEC = AgentSpec(
    name="supervisor",
    system_prompt=lambda task, ctx: load_prompt("supervisor.txt", ctx.store),
    user_message=user_message,
    tools=[GET_PROPOSAL, GET_OPEN_RISKS, ASK_REPLY, ASK_COMPLAINT, ASK_CAMPAIGN],
    submit=SUBMIT,
    check=check,
    task_id=lambda task: task["batch_id"],
    fallback=fallback,
    finalize=finalize,
    budget=Budget(max_steps=4, max_rejections=2, max_seconds=180),  # 안에서 일꾼이 돌므로 시간은 넉넉히
    temperature=0.2,
)


def coordinate_batch(batch: NotificationBatch | list[str], proposals: dict[str, Proposal], ctx: RunContext) -> BatchResult:
    """알림 묶음 하나를 조율한다. proposals: 할 일 id → 일꾼 제안 (이미 나와 있어야 한다)."""
    plan_ids = plan_ids_of(batch)
    conflicts = find_conflicts(plan_ids, proposals, ctx)
    if not conflicts:
        return BatchResult(plan_ids, dict(proposals), [])
    ctx = dataclasses.replace(ctx, call_budget=ctx.call_budget or CallBudget(SHARED_CALLS))
    batch_id = f"BATCH:{batch.slot_at.isoformat()}" if isinstance(batch, NotificationBatch) else "BATCH:" + ",".join(plan_ids)
    task = {
        "batch_id": batch_id, "plan_ids": plan_ids, "proposals": proposals, "conflicts": conflicts,
        "menu_names": {m.menu_id: m.name for m in ctx.snapshot.inputs.menus}, "asked": [], "revised": {},
    }
    result = runner.run(SPEC, task, ctx)
    content = result.content if result else fallback(task, ctx)
    final = dict(proposals)
    final.update(content["revised"])
    return BatchResult(
        plan_ids, final, conflicts, content["headline"], content["item_notes"],
        result.source if result else "FALLBACK", ctx.run_id,
    )
