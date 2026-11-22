"""단일 에이전트 A (비교용). 평가(Harness.evals)에서만 부른다. 운영 경로와 스위치에는 붙이지 않는다.

멀티 에이전트 하네스(B)와 같게 두는 것
  - 모델(설정의 기본 모델, HCX-005), 실행 루프 runner.run, 캐시·실행 기록·물러나기 방식
  - 읽기 전용 도구 함수 (reply_agent, complaint_agent, store_tools, voice_reply, improve_tip 의 것을 그대로 import)
  - 코드 검사(guards)와 근거 대조(grounding). 할 일마다 B 일꾼이 하는 코드 검사를 그대로 한다
  - 예산 총량: B 일꾼들이 같은 일에 쓰는 단계·거절·시간 상한의 합
  - 물러나기: 할 일마다 B 일꾼의 물러나기(기존 단일 호출, 템플릿)를 그대로 부른다
B 와 다른 것 (역할 분리 여부만)
  - 에이전트가 하나다. 묶음 안 모든 할 일을 한 대화에서 조사하고 한 번에 제출한다
  - 별도 LLM 검토(reply_critic)를 부르지 않는다. 프롬프트에 B 검토 기준과 같은 목록을 주고 제출 전에 스스로 확인하게 한다
  - 묶음 조율(conflicts + supervisor)이 없다. 프롬프트로 스스로 맞추게 한다

입구
  run_batch(items, ctx)            알림 묶음(답글·재주문 인사·반복 불만 진단) → 할 일 id → Proposal(없으면 None)
  prepare_voice(view, jobs, now)   음성 브리핑 준비(F3·F6 답글, F4 고칠 점) → voice_reply.write / improve_tip.suggest 와 같은 모양
  SYSTEM_TASKS                     Harness.evals.systems 가 "A" 로 읽는 일 이름 → 함수

검사에서 뺀 것: reply_agent.check, voice_reply.check 의 맨 끝 LLM 검토(reply_critic.inspect)와, 검토를 못 부를 때만 쓰는
금지어 정규식 대신 거르기. 그 앞의 코드 검사는 두 함수와 같은 순서로 여기 다시 적었다 (기존 파일을 고치지 않으려고).
기존 검사가 바뀌면 여기도 맞춰야 한다. 재주문 인사의 rejection_reason 은 LLM 이 아니라 B 와 같이 쓴다.
보내는 것: B 일꾼이 보내는 것과 같다 (리뷰 글은 mask_personal_info 를 거친 기존 메시지 함수로, 손님 키·주문 번호는 보내지 않음).
기록 이름: single_agent, voice_single_agent (CLOVA 사용 기록은 agent:single_agent …). 음성 쪽은 개발자 대시보드가
이름이 voice 로 시작하면 '음성 백엔드'로 나누므로 voice_ 를 앞에 둔다.
"""

import dataclasses
import datetime as dt

from app.analysis.review.hcx_classifier import mask_personal_info
from app.planner.data_shapes import PlanItem
from app.review_reply_writer import write_reply_with_clova as writer
from app.review_reply_writer.write_reply_with_clova import MAX_LENGTH, MIN_LENGTH, clean_answer
from Harness import guards, runner
from Harness.agents import complaint_agent, reply_agent
from Harness.grounding import Evidence
from Harness.spec import AgentSpec, Budget, Proposal, RunContext, Tool
from Harness.store_tools import DAY_CONTEXT, MENU_LIST, STORE_FACTS
from Harness.tools import array, load_prompt, obj, string
from voice.agents import improve_tip, voice_reply
from voice.audit import rules
from voice.context import run_context

BATCH_NAME = "single_agent"
VOICE_NAME = "voice_single_agent"
REPLY_TYPES = ("REVISIT_REPLY", "REORDER_NUDGE")
KIND_NAMES = {"REPLY": "리뷰 답글", "NUDGE": "재주문 인사"}
VOICE_KIND_NAMES = {"AUTO": "아쉬운 리뷰에 바로 올리는 답글", "SCHEDULED": "좋은 리뷰에 정해진 때 올리는 답글", "DRAFT": "사장님이 볼 답글 초안"}


def _texts(args: dict, key: str) -> list[str]:
    value = args.get(key) or []
    return [str(v).strip() for v in value if str(v).strip()] if isinstance(value, list) else []


def _sum_budget(budgets: list[Budget]) -> Budget:
    """B 일꾼들의 예산 상한을 더한다 (단계, 거절, 시간)."""
    return Budget(
        max_steps=sum(b.max_steps for b in budgets),
        max_rejections=sum(b.max_rejections for b in budgets),
        max_seconds=sum(b.max_seconds for b in budgets),
    )


def _safe(func, *args):
    """할 일 하나의 물러나기가 터져도 나머지 할 일은 계속 간다."""
    try:
        return func(*args)
    except Exception:  # noqa: BLE001 - runner 의 물러나기와 같은 태도
        return None


def _gather(reasons: list[tuple[str, str | None]]) -> str | None:
    """할 일별 거절 이유를 모은다. 하나라도 있으면 '[할 일 id] 이유' 들을 이어서 돌려준다."""
    found = [f"[{key}] {reason}" for key, reason in reasons if reason]
    return " / ".join(found) or None


def _by_key(rows: object, key: str) -> tuple[dict[str, dict], str | None]:
    """제출 목록 → {id: 항목}. 모양이 틀리거나 같은 id 가 두 번이면 이유."""
    if not isinstance(rows, list):
        return {}, "replies 는 목록이어야 해요"
    found: dict[str, dict] = {}
    for row in rows:
        if not isinstance(row, dict) or not str(row.get(key) or "").strip():
            return {}, f"replies 의 항목마다 {key} 가 있어야 해요"
        name = str(row[key]).strip()
        if name in found:
            return {}, f"{key} {name} 의 답글을 두 번 냈어요. 하나만 내 주세요"
        found[name] = row
    return found, None


def _coverage(found: dict[str, dict], expected: list[str], key: str) -> str | None:
    missing = [name for name in expected if name not in found]
    unknown = [name for name in found if name not in expected]
    reasons = []
    if missing:
        reasons.append(f"답글이 빠진 {key}: {', '.join(missing)}")
    if unknown:
        reasons.append(f"이 묶음에 없는 {key}: {', '.join(unknown)} (있는 것: {', '.join(expected)})")
    return "; ".join(reasons) or None


# ══ 알림 묶음 (기존 서버 경로) ══
#
# task 키
#   batch_id   "SINGLE:" + 할 일 id 들
#   items      답글·재주문 인사 task 목록 (reply_agent.task_for_plan_item 과 같은 모양)
#   diagnosis  반복 불만 진단 task (complaint_agent.task_for_plan_item 과 같은 모양) 또는 None


def batch_task(items: list[PlanItem], ctx: RunContext) -> dict:
    replies, diagnosis = [], None
    for item in items:
        if item.task_type in REPLY_TYPES:
            replies.append(reply_agent.task_for_plan_item(item, ctx))
        elif item.task_type == "REVIEW_FIX":
            if diagnosis is not None:
                raise ValueError("묶음 하나에 반복 불만 진단은 하나만 받아요")
            diagnosis = complaint_agent.task_for_plan_item(item, ctx)
        else:
            raise ValueError(f"단일 에이전트가 맡지 않는 할 일이에요: {item.task_type}")
    if not replies and diagnosis is None:
        raise ValueError("맡을 할 일이 없어요")
    return {"batch_id": "SINGLE:" + ",".join(i.plan_id for i in items), "items": replies, "diagnosis": diagnosis}


def _reply_task(task: dict, plan_id: object) -> dict | None:
    return next((item for item in task["items"] if item["plan_id"] == str(plan_id or "").strip()), None)


# ── 도구: 답글 도구는 plan_id 로 어느 할 일인지 고르고, 진단 도구는 묶음의 진단 task 를 쓴다 ──


def _per_reply(tool: Tool) -> Tool:
    def func(ctx: RunContext, task: dict, args: dict) -> object:
        item = _reply_task(task, args.get("plan_id"))
        if item is None:
            ids = ", ".join(i["plan_id"] for i in task["items"])
            return {"error": f"plan_id 를 이 묶음의 답글 할 일 중에서 골라 주세요: {ids}"}
        return tool.func(ctx, item, args)

    parameters = obj({"plan_id": string("어느 답글 할 일인지 (할 일 목록의 plan_id 그대로)")})
    return Tool(tool.name, f"{tool.description}. plan_id 로 할 일을 고른다", parameters, func)


def _for_diagnosis(tool: Tool) -> Tool:
    def func(ctx: RunContext, task: dict, args: dict) -> object:
        if task.get("diagnosis") is None:
            return {"error": "이 묶음에는 진단할 반복 불만이 없어요"}
        return tool.func(ctx, task["diagnosis"], args)

    return Tool(tool.name, tool.description, tool.parameters, func)


REPLY_TOOLS = [_per_reply(reply_agent.CUSTOMER_PATTERN), _per_reply(reply_agent.RECENT_SAME_COMPLAINTS), MENU_LIST, STORE_FACTS]
DIAGNOSIS_TOOLS = [_for_diagnosis(complaint_agent.RISK_REVIEWS), _for_diagnosis(complaint_agent.ORDERS_BY_HOUR),
                   _for_diagnosis(complaint_agent.STAFF_SHIFTS), DAY_CONTEXT]

REPLY_ITEM = obj(
    {"plan_id": string("할 일 목록의 plan_id 그대로"), **reply_agent.SUBMIT.parameters["properties"]},
    required=["plan_id", "text", "quoted_review_words"],
)
SUBMIT_BATCH = Tool(
    "submit_batch_all",
    "묶음 안 모든 할 일의 결과를 한 번에 제출한다",
    obj(
        {
            "replies": array(REPLY_ITEM, "답글·재주문 인사 할 일마다 하나씩. 답글 할 일이 없으면 빈 목록"),
            "diagnosis": {**complaint_agent.SUBMIT.parameters, "description": "반복 불만 진단. 진단할 일이 없으면 빼"},
        },
        required=["replies"],
    ),
)


# ── 프롬프트 ──


def batch_system_prompt(task: dict, ctx: RunContext) -> str:
    kinds = list(dict.fromkeys(item["kind"] for item in task["items"]))
    bases = [writer.load_prompt(reply_agent.BASE_PROMPTS[kind], ctx.store) for kind in kinds]  # reply_agent.system_prompt 와 같게
    return "\n\n".join([*bases, load_prompt("single_agent.txt", ctx.store)])


def batch_user_message(task: dict, ctx: RunContext) -> str:
    rows = ["알림 묶음 하나에 들어 있는 할 일이야. 모두 끝내고 submit_batch_all 로 한 번에 제출해."]
    number = 0
    for item in task["items"]:
        number += 1
        rows.append(f"\n[할 일 {number}] plan_id: {item['plan_id']} ({KIND_NAMES[item['kind']]})")
        if item["kind"] == "REPLY":
            review = reply_agent.find_review(ctx, item["review_id"])
            rows.append(writer.reply_message(review, item.get("revisit_class")) if review else "(리뷰를 찾지 못했어요)")
        else:
            rows.append(writer.nudge_message(reply_agent._menus(ctx)))
    diagnosis = task.get("diagnosis")
    if diagnosis is not None:
        number += 1
        text = complaint_agent.user_message(diagnosis, ctx).replace("submit_diagnosis 로", "submit_batch_all 의 diagnosis 로")
        rows.append(f"\n[할 일 {number}] plan_id: {diagnosis['plan_id']} (반복 불만 진단)\n{text}")
    return "\n".join(rows)


# ── 검사 ──


def reply_code_check(args: dict, item: dict, ctx: RunContext) -> str | None:
    """reply_agent.check 에서 LLM 검토(reply_critic) 앞까지의 코드 검사. 재주문 인사는 기존 rejection_reason 까지."""
    text = clean_answer(str(args.get("text") or ""))
    review = reply_agent.find_review(ctx, item.get("review_id"))
    quoted, menus, facts = _texts(args, "quoted_review_words"), _texts(args, "menus_mentioned"), _texts(args, "facts_used")
    reason = guards.first(
        guards.length(text, MIN_LENGTH, MAX_LENGTH, "답글"),
        guards.placeholder(text),
        guards.not_in(menus, reply_agent._menus(ctx), "메뉴 이름"),
        guards.not_in(facts, ctx.store_facts, "가게 사실(get_store_facts 에 있는 문장만 쓸 수 있어요)"),
    )
    if reason:
        return reason
    if item["kind"] == "NUDGE":
        return writer.rejection_reason(text, reply_agent._menus(ctx))
    if not quoted:
        return "quoted_review_words 에 답글이 대답한 리뷰 속 말을 1개 이상 적어 주세요"
    missing = [q for q in quoted if review is None or q not in review.text]
    if missing:
        original = mask_personal_info(review.text) if review else ""
        return (f"quoted_review_words 의 {', '.join(repr(q) for q in missing)} 는 리뷰에 글자 그대로 없어요. "
                f'리뷰 원문 "{original}" 에서 띄어쓰기·문장부호까지 그대로 옮겨 주세요. 답글(text)은 바꾸지 않아도 돼요')
    return None


def batch_check(args: dict, evidence: Evidence, task: dict, ctx: RunContext, notes: list[str]) -> str | None:
    expected = [item["plan_id"] for item in task["items"]]
    found, shape = _by_key(args.get("replies"), "plan_id")
    if shape:
        return shape
    reasons: list[tuple[str, str | None]] = [("묶음", _coverage(found, expected, "plan_id"))]
    reasons += [(item["plan_id"], reply_code_check(found[item["plan_id"]], item, ctx))
                for item in task["items"] if item["plan_id"] in found]
    diagnosis = task.get("diagnosis")
    if diagnosis is not None:
        submitted = args.get("diagnosis")
        if not isinstance(submitted, dict):
            reasons.append((diagnosis["plan_id"], "diagnosis 가 빠졌어요. 반복 불만 진단도 함께 내 주세요"))
        else:
            reasons.append((diagnosis["plan_id"], complaint_agent.check(submitted, evidence, diagnosis, ctx, notes)))
    return _gather(reasons)


def batch_finalize(args: dict, task: dict, ctx: RunContext) -> dict:
    found, _ = _by_key(args.get("replies"), "plan_id")
    diagnosis = task.get("diagnosis")
    return {
        "replies": {item["plan_id"]: reply_agent.finalize(found[item["plan_id"]], item, ctx) for item in task["items"]},
        "diagnosis": complaint_agent.finalize(args["diagnosis"], diagnosis, ctx) if diagnosis is not None else None,
    }


def batch_fallback(task: dict, ctx: RunContext) -> dict | None:
    """할 일마다 B 일꾼의 물러나기 (기존 단일 호출, 이유 한 줄)."""
    diagnosis = task.get("diagnosis")
    content = {
        "replies": {item["plan_id"]: _safe(reply_agent.fallback, item, ctx) for item in task["items"]},
        "diagnosis": _safe(complaint_agent.fallback, diagnosis, ctx) if diagnosis is not None else None,
    }
    if content["diagnosis"] is None and not any(content["replies"].values()):
        return None
    return content


SINGLE_BATCH_SPEC = AgentSpec(
    name=BATCH_NAME,
    system_prompt=batch_system_prompt,
    user_message=batch_user_message,
    tools=REPLY_TOOLS + DIAGNOSIS_TOOLS,
    submit=SUBMIT_BATCH,
    check=batch_check,
    task_id=lambda task: task["batch_id"],
    fallback=batch_fallback,
    finalize=batch_finalize,
    budget=_sum_budget([reply_agent.SPEC.budget, reply_agent.SPEC.budget, complaint_agent.SPEC.budget]),  # 답글 2 + 진단 1 기준
    temperature=0.3,
)


def batch_spec(task: dict) -> AgentSpec:
    """이 묶음에 맞춘 스펙: 맡은 일의 도구만, 예산은 B 일꾼 예산의 합, 온도는 B 일꾼과 같게(섞이면 그 사이)."""
    replies, diagnosis = task["items"], task.get("diagnosis") is not None
    budgets = [reply_agent.SPEC.budget] * len(replies) + ([complaint_agent.SPEC.budget] if diagnosis else [])
    if replies and diagnosis:
        temperature = SINGLE_BATCH_SPEC.temperature
    else:
        temperature = reply_agent.SPEC.temperature if replies else complaint_agent.SPEC.temperature
    return dataclasses.replace(
        SINGLE_BATCH_SPEC,
        tools=(REPLY_TOOLS if replies else []) + (DIAGNOSIS_TOOLS if diagnosis else []),
        budget=_sum_budget(budgets),
        temperature=temperature,
    )


def split_batch(proposal: Proposal | None, task: dict) -> dict[str, Proposal | None]:
    """묶음 제안 하나 → 할 일 id 마다 Proposal (B 일꾼 결과와 같은 모양으로 비교하려고)."""
    ids = [item["plan_id"] for item in task["items"]]
    diagnosis = task.get("diagnosis")
    if diagnosis is not None:
        ids.append(diagnosis["plan_id"])
    if proposal is None:
        return {plan_id: None for plan_id in ids}
    contents = dict(proposal.content["replies"])
    if diagnosis is not None:
        contents[diagnosis["plan_id"]] = proposal.content["diagnosis"]
    return {
        plan_id: Proposal(proposal.agent, plan_id, contents[plan_id], proposal.source, proposal.run_id,
                          list(proposal.evidence), list(proposal.notes)) if contents.get(plan_id) is not None else None
        for plan_id in ids
    }


def run_batch(items: list[PlanItem], ctx: RunContext) -> dict[str, Proposal | None]:
    """알림 묶음 하나를 에이전트 하나로 끝낸다. 할 일 id → Proposal (만들지 못한 할 일은 None)."""
    task = batch_task(items, ctx)
    return split_batch(runner.run(batch_spec(task), task, ctx), task)


def _one(item: PlanItem, ctx: RunContext, **_ignored) -> Proposal | None:
    """할 일 하나만 든 묶음 (B 의 draft·diagnose 와 같은 자리에서 부를 수 있게). supervisor_note 같은 조율 지시는 받지 않는다."""
    return run_batch([item], ctx)[item.plan_id]


# ══ 음성 브리핑 준비 (voice 경로) ══
#
# task 키
#   date     오늘 YYYY-MM-DD (고칠 점 task 와 같다)
#   replies  [{kind: AUTO|SCHEDULED|DRAFT, review_id, occasion}] (voice_reply task 와 같은 모양)
#   tip      고칠 점도 쓰는지 (최근 4주 아쉬운 리뷰가 있을 때)


def _voice_reply_task(task: dict, review_id: object) -> dict | None:
    return next((item for item in task["replies"] if item["review_id"] == str(review_id or "").strip()), None)


def _occasion(ctx: RunContext, task: dict, args: dict) -> object:
    item = _voice_reply_task(task, args.get("review_id"))
    if item is None:
        ids = ", ".join(i["review_id"] for i in task["replies"])
        return {"error": f"review_id 를 이 준비의 답글 할 일 중에서 골라 주세요: {ids}"}
    return voice_reply.reply_occasion(ctx, item, args)


VOICE_REPLY_TOOLS = [
    voice_reply.MENU_LIST, voice_reply.STORE_FACTS,
    Tool(voice_reply.REPLY_OCCASION.name, f"{voice_reply.REPLY_OCCASION.description}. review_id 로 답글을 고른다",
         obj({"review_id": string("어느 리뷰의 답글인지 (할 일 목록의 review_id 그대로)")}), _occasion),
]
VOICE_TIP_TOOLS = [improve_tip.NEGATIVE_REVIEWS, improve_tip.REVIEW_COUNTS]

VOICE_REPLY_ITEM = obj(
    {"review_id": string("할 일 목록의 review_id 그대로"), **reply_agent.SUBMIT.parameters["properties"]},
    required=["review_id", "text", "quoted_review_words"],
)
SUBMIT_VOICE = Tool(
    "submit_voice_all",
    "브리핑 준비의 답글과 고칠 점을 한 번에 제출한다",
    obj(
        {
            "replies": array(VOICE_REPLY_ITEM, "답글 할 일마다 하나씩. 답글 할 일이 없으면 빈 목록"),
            "tip": {**improve_tip.SUBMIT.parameters, "description": "고칠 점. 할 일 목록에 고칠 점이 없으면 빼"},
        },
        required=["replies"],
    ),
)


def voice_system_prompt(task: dict, ctx: RunContext) -> str:
    parts = [writer.load_prompt("review_reply_prompt.txt", ctx.store)] if task["replies"] else []  # voice_reply.system_prompt 와 같게
    return "\n\n".join([*parts, load_prompt("single_voice_agent.txt", ctx.store)])


def voice_user_message(task: dict, ctx: RunContext) -> str:
    rows = [f"오늘: {ctx.now:%Y-%m-%d}", "브리핑 준비 때 할 일이야. 모두 끝내고 submit_voice_all 로 한 번에 제출해."]
    number = 0
    for item in task["replies"]:
        number += 1
        detail = voice_reply.user_message(item, ctx).split("\n", 1)[1]  # 첫 줄(오늘)은 위에 한 번만
        rows.append(f"\n[할 일 {number}] review_id: {item['review_id']} ({VOICE_KIND_NAMES[item['kind']]})\n{detail}")
    if task.get("tip"):
        number += 1
        rows.append(f"\n[할 일 {number}] 고칠 점\n최근 4주 아쉬운 리뷰를 보고 가장 먼저 고칠 점 한 가지를 tip 으로 내 줘.")
    return "\n".join(rows)


def voice_reply_code_check(args: dict, item: dict, ctx: RunContext) -> str | None:
    """voice_reply 의 1차 코드 감사 (감사팀 rules.reply_code, LLM 검토 앞까지). 같은 검사를 복사해 두지 않고 그대로 부른다."""
    return rules.reply_code(args, item, ctx)


def voice_check(args: dict, evidence: Evidence, task: dict, ctx: RunContext, notes: list[str]) -> str | None:
    expected = [item["review_id"] for item in task["replies"]]
    found, shape = _by_key(args.get("replies"), "review_id")
    if shape:
        return shape
    reasons: list[tuple[str, str | None]] = [("준비", _coverage(found, expected, "review_id"))]
    reasons += [(item["review_id"], voice_reply_code_check(found[item["review_id"]], item, ctx))
                for item in task["replies"] if item["review_id"] in found]
    if task.get("tip"):
        tip = args.get("tip")
        if not isinstance(tip, dict):
            reasons.append(("고칠 점", "tip 이 빠졌어요. 고칠 점도 함께 내 주세요"))
        else:
            reasons.append(("고칠 점", rules.improve_tip(tip, evidence, {"date": task["date"]}, ctx, notes)))
    return _gather(reasons)


def voice_finalize(args: dict, task: dict, ctx: RunContext) -> dict:
    found, _ = _by_key(args.get("replies"), "review_id")
    tip = args.get("tip") if task.get("tip") else None
    return {
        "replies": {item["review_id"]: voice_reply.finalize(found[item["review_id"]], item, ctx) for item in task["replies"]},
        "tip": {"tip": str(tip.get("tip") or "").strip()} if isinstance(tip, dict) else None,
    }


def voice_fallback(task: dict, ctx: RunContext) -> dict:
    """할 일마다 B 의 물러나기 (주제·이유별 템플릿, 고칠 점 템플릿)."""
    return {
        "replies": {item["review_id"]: _safe(voice_reply.fallback, item, ctx) for item in task["replies"]},
        "tip": _safe(improve_tip.fallback, {"date": task["date"]}, ctx) if task.get("tip") else None,
    }


SINGLE_VOICE_SPEC = AgentSpec(
    name=VOICE_NAME,
    system_prompt=voice_system_prompt,
    user_message=voice_user_message,
    tools=VOICE_REPLY_TOOLS + VOICE_TIP_TOOLS,
    submit=SUBMIT_VOICE,
    check=voice_check,
    task_id=lambda task: f"SINGLE_VOICE:{task['date']}",
    fallback=voice_fallback,
    finalize=voice_finalize,
    budget=_sum_budget([voice_reply.SPEC.budget, improve_tip.SPEC.budget]),  # 답글 1 + 고칠 점 1 기준
    temperature=0.4,
)


def voice_spec(task: dict) -> AgentSpec:
    """이 준비에 맞춘 스펙: 맡은 일의 도구만, 예산은 B(답글마다 voice_reply, 고칠 점 improve_tip)의 합."""
    replies, tip = task["replies"], bool(task.get("tip"))
    budgets = [voice_reply.SPEC.budget] * len(replies) + ([improve_tip.SPEC.budget] if tip else [])
    if replies and tip:
        temperature = SINGLE_VOICE_SPEC.temperature
    else:
        temperature = voice_reply.SPEC.temperature if replies else improve_tip.SPEC.temperature
    return dataclasses.replace(
        SINGLE_VOICE_SPEC,
        tools=(VOICE_REPLY_TOOLS if replies else []) + (VOICE_TIP_TOOLS if tip else []),
        budget=_sum_budget(budgets),
        temperature=temperature,
    )


def prepare_voice(view, jobs: list[dict], now: dt.datetime, *, tip: bool = True) -> dict:
    """브리핑 준비 때 할 일을 에이전트 하나로 끝낸다.

    jobs: [{"review": 리뷰 dict, "kind": AUTO|SCHEDULED|DRAFT, "occasion": dict|None}]
    돌려주는 것: {"replies": {review_id: {text, source, notes}}, "tip": {text, source}}
      voice_reply.write, improve_tip.suggest 와 같은 모양. 에이전트·물러나기가 모두 실패하면 템플릿(source TEMPLATE).
      평가에서만 부르므로 VOICE_AGENT_* 스위치는 보지 않는다.
    tip=False 면 고칠 점은 맡기지 않는다 (답글만 비교하는 평가에서 B 의 voice_reply.write 와 같은 일만 하게).
    """
    negatives = improve_tip.negatives(view, now) if tip else []
    task = {
        "date": f"{now:%Y-%m-%d}",
        "replies": [{"kind": job["kind"], "review_id": job["review"]["id"], "occasion": job.get("occasion")} for job in jobs],
        "tip": bool(negatives),
    }
    result = {"replies": {}, "tip": {"text": None, "source": "NONE"}}
    proposal = runner.run(voice_spec(task), task, run_context(view, now)) if (task["replies"] or task["tip"]) else None
    content = proposal.content if proposal else {"replies": {}, "tip": None}
    for job in jobs:
        written = content["replies"].get(job["review"]["id"])
        if written is None:
            result["replies"][job["review"]["id"]] = {"text": voice_reply.template(view, job["review"], job.get("occasion")),
                                                      "source": "TEMPLATE", "notes": []}
        else:
            result["replies"][job["review"]["id"]] = {"text": written["text"], "source": proposal.source, "notes": list(proposal.notes)}
    if task["tip"]:
        tip = content.get("tip")
        result["tip"] = ({"text": tip["tip"], "source": proposal.source} if tip else
                         {"text": improve_tip.template(negatives), "source": "TEMPLATE"})
    return result


# Harness.evals.systems 가 "A" 로 읽는다. 일 이름은 systems.TASKS 와 같다
SYSTEM_TASKS = {
    "draft": _one,
    "diagnose": _one,
    "batch": run_batch,
    "voice_prepare": prepare_voice,
}
