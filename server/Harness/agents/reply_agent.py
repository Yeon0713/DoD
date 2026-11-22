"""① 리뷰 응대 에이전트: 답글 초안, 재주문 인사, 다시 쓰기.

task 키
  kind            "REPLY" | "NUDGE" | "REWRITE"
  plan_id         할 일 id (다시 쓰기는 부르는 쪽이 정한 id)
  review_id       답글을 달 리뷰 (재주문 인사는 물러나기에 쓰는 그 손님의 가장 최근 리뷰, 다시 쓰기는 있으면 참고)
  revisit_class   QUICK | WEEKLY | MONTHLY | BASIC (답글)
  customer_key    손님 키. 도구가 쓰고 모델에게는 보여 주지 않는다
  text            다시 쓰기: 사장님이 보고 있는 답글
  style           다시 쓰기: "short" | "polite" (기존 버튼)
  instruction     다시 쓰기: 사장님이 직접 적은 지시 (예: "다음 주문 때 음료 드린다고 해 줘")
  supervisor_note supervisor 가 준 조율 지시 (있을 때)

검사 순서
  1. 코드 검사: 길이, 빈칸, quoted_review_words 가 실제 리뷰에 있는지, 메뉴·사실 메모 대조, 다시 쓰기는 사장님 숫자 유지
  2. 재주문 인사: 기존 rejection_reason (보상 약속, 기억하는 척, 지어낸 사정, 메뉴 이름) 을 그대로 쓴다. 리뷰 답글이 아니라 LLM 검토는 하지 않는다
  3. 답글·다시 쓰기: LLM 검토(reply_critic.inspect). 보상 제안과 고칠 점은 좁은 질문으로 따로 묻고 코드가 판정한다.
     검토를 부를 수 없으면 '검토 안 됨'을 남기고 기존 금지어 정규식으로 대신 거른다
물러나기: 기존 write_one() / rewrite(). 자유 지시만 있는 다시 쓰기는 기존 함수가 없어 None.
"""

import dataclasses
import datetime as dt

from app.analysis.review.hcx_classifier import mask_personal_info
from app.planner.data_shapes import PlanItem, Review
from app.planner.rule_complaint_fix import COMPLAINT_NAMES
from app.review_reply_writer import write_reply_with_clova as writer
from app.review_reply_writer.write_reply_with_clova import MAX_LENGTH, MIN_LENGTH, clean_answer
from Harness import guards, runner
from Harness.agents import reply_critic
from Harness.grounding import Evidence
from Harness.spec import AgentSpec, Budget, Proposal, RunContext, Tool
from Harness.store_tools import MENU_LIST, STORE_FACTS, day_label
from Harness.tools import array, load_prompt, obj, string

BASE_PROMPTS = {"REPLY": "review_reply_prompt.txt", "NUDGE": "reorder_nudge_prompt.txt", "REWRITE": "rewrite_reply_prompt.txt"}
CYCLE_NAMES = {"WEEKLY": "매주 주문하는 단골", "MONTHLY": "한 달에 한 번 주문하는 단골", "NONE": "정해진 주기 없음"}
RECENT_DAYS = 7


# ── task 만들기 ──


def find_review(ctx: RunContext, review_id: str | None) -> Review | None:
    return next((r for r in ctx.snapshot.reviews if r.review_id == review_id), None) if review_id else None


def task_for_plan_item(item: PlanItem, ctx: RunContext) -> dict:
    """답글(REVISIT_REPLY) / 재주문 인사(REORDER_NUDGE) 할 일 → task."""
    if item.task_type == "REVISIT_REPLY":
        review = find_review(ctx, item.basis.ref_id)
        return {"kind": "REPLY", "plan_id": item.plan_id, "review_id": item.basis.ref_id,
                "revisit_class": item.revisit_class, "customer_key": review.customer_key if review else None}
    if item.task_type == "REORDER_NUDGE":
        customer = item.basis.ref_id
        own = [r for r in ctx.snapshot.reviews if r.customer_key == customer and r.written_at <= item.approval_request_at]
        latest = max(own, key=lambda r: r.written_at) if own else None
        return {"kind": "NUDGE", "plan_id": item.plan_id, "review_id": latest.review_id if latest else None,
                "customer_key": customer}
    raise ValueError(f"리뷰 응대 할 일이 아니에요: {item.task_type}")


# ── 도구 ──


def customer_pattern(ctx: RunContext, task: dict, args: dict) -> dict:
    key = task.get("customer_key")
    if not key:
        return {"note": "주문 이력과 이어지지 않은 손님이에요"}
    cycles = [c for c in ctx.snapshot.customer_cycles if c.customer_key == key and c.computed_at <= ctx.now]
    cycle = max(cycles, key=lambda c: c.computed_at) if cycles else None
    orders = sorted(o.ordered_at for o in ctx.snapshot.inputs.orders if o.customer_key == key and o.ordered_at <= ctx.now)
    return {
        "cycle": CYCLE_NAMES.get(cycle.cycle, "정해진 주기 없음") if cycle else "정해진 주기 없음",
        "intervals_days": cycle.intervals_days[-5:] if cycle else [],
        "orders": len(orders),
        "last_order": day_label(orders[-1].date()) if orders else None,
    }


def recent_same_complaints(ctx: RunContext, task: dict, args: dict) -> dict:
    review = find_review(ctx, task.get("review_id"))
    if review is None or review.label is None or not review.label.complaint_types:
        return {"note": "이 리뷰에는 불만이 없어요"}
    since = ctx.now - dt.timedelta(days=RECENT_DAYS)
    found = []
    for complaint in review.label.complaint_types:
        others = [
            r for r in ctx.snapshot.reviews
            if r.review_id != review.review_id and r.label is not None and complaint in r.label.complaint_types
            and since < r.written_at <= ctx.now
        ]
        found.append({
            "complaint": COMPLAINT_NAMES[complaint],
            "other_reviews_last_7_days": len(others),
            "examples": [mask_personal_info(r.text)[:60] for r in others[:3]],
        })
    return {"complaints": found}


CUSTOMER_PATTERN = Tool("get_customer_pattern", "이 손님의 주문 주기와 주문 횟수 (손님 id 는 주지 않는다)", obj({}), customer_pattern)
RECENT_SAME_COMPLAINTS = Tool(
    "get_recent_same_complaints", "최근 7일 같은 불만 리뷰가 몇 건 더 있었는지와 짧은 예시", obj({}), recent_same_complaints,
)
SUBMIT = Tool(
    "submit_reply",
    "완성한 답글을 제출한다",
    obj(
        {
            "text": string("답글 전체 (머리말, 따옴표 없이)"),
            "quoted_review_words": array(string("리뷰 속 말"), "답글이 대답한 리뷰 속 말을 리뷰에서 글자 그대로 1~3개. 재주문 인사는 빈 목록"),
            "menus_mentioned": array(string("메뉴 이름"), "답글에 쓴 메뉴 이름"),
            "facts_used": array(string("가게 사실"), "답글에 쓴 가게 사실 (get_store_facts 문장 그대로)"),
        },
        required=["text", "quoted_review_words"],
    ),
)


# ── 프롬프트 ──


def system_prompt(task: dict, ctx: RunContext) -> str:
    base = writer.load_prompt(BASE_PROMPTS[task["kind"]], ctx.store)  # 팀이 다듬어 온 답글 말투 프롬프트를 그대로 쓴다
    return f"{base}\n\n{load_prompt('reply_agent.txt', ctx.store)}"


def review_facts(task: dict, ctx: RunContext) -> str:
    review = find_review(ctx, task.get("review_id"))
    return writer.review_facts(review, task.get("revisit_class")) if review else ""


def user_message(task: dict, ctx: RunContext) -> str:
    kind = task["kind"]
    if kind == "REPLY":
        text = writer.reply_message(find_review(ctx, task["review_id"]), task.get("revisit_class"))
    elif kind == "NUDGE":
        text = writer.nudge_message(_menus(ctx))
    else:
        rows = []
        if task.get("style"):
            rows.append(f"고칠 방향: {writer.STYLE_NAMES[task['style']]}")
        if task.get("instruction"):
            rows.append(f"사장님 지시: {task['instruction']}")
        rows.append(f"\n지금 답글: {task['text']}")
        facts = review_facts(task, ctx)
        if facts:
            rows.append(f"\n참고할 리뷰\n{facts}")
        text = "\n".join(rows)
    if task.get("supervisor_note"):
        text += f"\n\n조율 지시(같은 알림에 함께 가는 다른 할 일과 맞추기): {task['supervisor_note']}"
    return text


def _menus(ctx: RunContext) -> list[str]:
    return [menu.name for menu in ctx.snapshot.inputs.menus]


# ── 검사 ──


def _texts(args: dict, key: str) -> list[str]:
    value = args.get(key) or []
    return [str(v).strip() for v in value if str(v).strip()] if isinstance(value, list) else []


def check(args: dict, evidence: Evidence, task: dict, ctx: RunContext, notes: list[str]) -> str | None:
    kind = task["kind"]
    text = clean_answer(str(args.get("text") or ""))
    review = find_review(ctx, task.get("review_id"))
    quoted, menus, facts = _texts(args, "quoted_review_words"), _texts(args, "menus_mentioned"), _texts(args, "facts_used")

    reason = guards.first(
        guards.length(text, MIN_LENGTH, MAX_LENGTH, "답글"),
        guards.placeholder(text),
        guards.not_in(menus, _menus(ctx), "메뉴 이름"),
        guards.not_in(facts, ctx.store_facts, "가게 사실(get_store_facts 에 있는 문장만 쓸 수 있어요)"),
    )
    if reason:
        return reason

    if kind == "NUDGE":
        return writer.rejection_reason(text, _menus(ctx))

    if kind == "REPLY":
        if not quoted:
            return "quoted_review_words 에 답글이 대답한 리뷰 속 말을 1개 이상 적어 주세요"
        missing = [q for q in quoted if review is None or q not in review.text]
        if missing:
            original = mask_personal_info(review.text) if review else ""
            return (f"quoted_review_words 의 {', '.join(repr(q) for q in missing)} 는 리뷰에 글자 그대로 없어요. "
                    f'리뷰 원문 "{original}" 에서 띄어쓰기·문장부호까지 그대로 옮겨 주세요. 답글(text)은 바꾸지 않아도 돼요')
    if kind == "REWRITE":
        reason = guards.numbers_kept(task["text"], text)
        if reason:
            return reason

    instruction = task.get("instruction")
    verdict = reply_critic.inspect(
        text, ctx, review_text=mask_personal_info(review.text) if review else None,
        has_complaint=bool(review and review.label and review.label.complaint_types),
        regular=task.get("revisit_class") in ("WEEKLY", "MONTHLY"), owner_instruction=instruction,
    )
    if verdict is None:  # 검토를 부를 수 없을 때는 기존 금지어 정규식으로 대신 거른다 (보상은 inspect 가 이미 걸렀다)
        notes.append("검토 안 됨")
        return guards.first(
            guards.memory(text),
            None if any(fact in text for fact in facts) else guards.made_up_fact(text),
        )
    if not verdict.ok:
        return "검토에서 걸렸어요: " + "; ".join(v.describe() for v in verdict.violations)
    return None


def finalize(args: dict, task: dict, ctx: RunContext) -> dict:
    return {"kind": task["kind"], "text": clean_answer(str(args.get("text") or ""))}


# ── 물러나기: 기존 단일 호출 ──


def _plan_item(ctx: RunContext, plan_id: str) -> PlanItem | None:
    plan = ctx.snapshot.plan
    return next((i for i in plan.plan_items if i.plan_id == plan_id), None) if plan else None


def fallback(task: dict, ctx: RunContext) -> dict | None:
    review = find_review(ctx, task.get("review_id"))
    if task["kind"] == "REWRITE":
        if not task.get("style"):
            return None
        text = writer.rewrite(task["text"], task["style"], ctx.store, review, post=ctx.post)
    else:
        item = _plan_item(ctx, task["plan_id"])
        if item is None or review is None:
            return None
        text = writer.write_one(item, review, ctx.store, _menus(ctx), post=ctx.post)
    return {"kind": task["kind"], "text": text} if text else None


SPEC = AgentSpec(
    name="reply_agent",
    system_prompt=system_prompt,
    user_message=user_message,
    tools=[CUSTOMER_PATTERN, RECENT_SAME_COMPLAINTS, MENU_LIST, STORE_FACTS],
    submit=SUBMIT,
    check=check,
    task_id=lambda task: task["plan_id"],
    fallback=fallback,
    finalize=finalize,
    budget=Budget(max_steps=5, max_rejections=2, max_seconds=40),
    temperature=0.5,
    cache_scope=lambda task: task.get("plan_id"),  # 재주문 인사의 손님은 user 메시지에 없고 도구만 읽는다 (H2)
)
# 다시 쓰기는 사장님이 버튼을 누르고 기다리므로 더 짧게
REWRITE_SPEC = dataclasses.replace(SPEC, name="reply_agent_rewrite", budget=Budget(max_steps=3, max_rejections=2, max_seconds=15))


def draft(item: PlanItem, ctx: RunContext, *, supervisor_note: str | None = None) -> Proposal | None:
    """답글 / 재주문 인사 할 일의 초안."""
    task = task_for_plan_item(item, ctx)
    if supervisor_note:
        task["supervisor_note"] = supervisor_note
    return runner.run(SPEC, task, ctx)


def rewrite(
    text: str, ctx: RunContext, *, style: str | None = None, instruction: str | None = None,
    review_id: str | None = None, plan_id: str = "REWRITE",
) -> Proposal | None:
    """사장님이 보고 있는 답글을 다시 쓴다. style("short"|"polite")이나 instruction 중 하나는 있어야 한다."""
    if not style and not instruction:
        raise ValueError("style 이나 instruction 중 하나는 있어야 해요")
    task = {"kind": "REWRITE", "plan_id": plan_id, "text": text, "style": style, "instruction": instruction, "review_id": review_id}
    return runner.run(REWRITE_SPEC, task, ctx)
