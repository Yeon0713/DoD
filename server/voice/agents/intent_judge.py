"""F8 뜻 판정 에이전트. 규칙(dialog/intent_rules)으로 못 가른 말만 여기로 온다.

호출어가 없어서 주방 대화가 그대로 들어온다. 도나에게 한 말이 아니면 not_for_donna, 도나에게 한 말인데 뜻을 모르면 unknown.
애매하면 not_for_donna (틀리게 답하는 것보다 가만히 있는 편이 낫다).
예산: 1단계, 3초 (말로 하는 대화라 늦으면 못 쓴다). 첫 요청부터 submit_intent 를 강제한다.
엄격한 예산(Budget.strict): 호출 제한 시간 = 남은 예산, 429·강제 제출 400 이면 다시 묻지 않고 물러난다 (최악 3초 남짓).
물러나기: 규칙의 heuristic (None 을 돌려주면 부르는 쪽이 정한다).
"""

from Harness import runner
from Harness.grounding import Evidence
from Harness.spec import AgentSpec, Budget, RunContext, Tool
from Harness.tools import obj, string
from voice import config
from voice.agents import load_prompt
from voice.context import VoiceStore, run_context

INTENTS = [
    "briefing.start", "briefing.next", "briefing.repeat", "briefing.restart", "briefing.jump",
    "detail.show", "detail.read", "detail.back", "permission.yes", "permission.no", "stop", "question", "unknown", "not_for_donna",
    "navigate.sales", "navigate.week", "navigate.settings",
    "action.approve", "action.edit", "action.cancel", "action.revise",
    # 알바생 (2026-11-18, voice/staff_orders.py)
    "staff.order", "staff.status", "staff.cancel", "staff.invite", "staff.remove", "staff.share", "staff.list", "staff.manual",
    "staff.yes", "staff.no", "staff.daily",
]
JUMP_TARGETS = ["schedule", "reviews", "negative", "positive", "scheduling"]
STAFF_SLOTS = ("staff_name", "task_title", "task_repeat", "task_kind")

SUBMIT = Tool(
    "submit_intent",
    "사장님 말의 뜻을 제출한다",
    obj(
        {
            "intent": string("뜻", enum=INTENTS),
            "owner_said": string("받아쓰기 오타를 바로잡은 사장님 말"),
            "jump_to": string("briefing.jump 일 때 건너뛸 단계", enum=JUMP_TARGETS),
            "staff_name": string("staff.order·staff.invite·staff.remove 일 때 알바생 이름. 모두에게면 '모두', 말하지 않았으면 빈 글자"),
            "task_title": string("staff.order 일 때 알바생 화면에 보일 짧은 할 일"),
            "task_repeat": string("staff.order 일 때 오늘만(today) 또는 매일(daily)", enum=["today", "daily"]),
            "task_kind": string("staff.order 일 때 할 것(do) 또는 하지 말 것(dont)", enum=["do", "dont"]),
        },
        required=["intent", "owner_said"],
    ),
)


def user_message(task: dict, ctx: RunContext) -> str:
    return f"직전 상황: {task['situation']}\n들어온 말: \"{task['text']}\"\n뜻을 submit_intent 로 내 줘."


def check(args: dict, evidence: Evidence, task: dict, ctx: RunContext, notes: list[str]) -> str | None:
    if args.get("intent") not in INTENTS:
        return f"intent 는 다음 중 하나여야 해요: {', '.join(INTENTS)}"
    if args["intent"] == "briefing.jump" and args.get("jump_to") not in JUMP_TARGETS:
        return f"briefing.jump 이면 jump_to 를 {', '.join(JUMP_TARGETS)} 중에서 골라 주세요"
    if args["intent"] == "staff.order" and not (args.get("task_title") or "").strip():
        return "staff.order 이면 task_title 에 알바생 화면에 보일 할 일을 적어 주세요"
    return None


SPEC = AgentSpec(
    name="voice_intent",
    system_prompt=lambda task, ctx: load_prompt("intent_judge.txt", ctx.store),
    user_message=user_message,
    tools=[],
    submit=SUBMIT,
    check=check,
    task_id=lambda task: task["text"],
    budget=Budget(max_steps=1, max_rejections=1, max_seconds=3, strict=True),
    temperature=0,
)


def judge(view: VoiceStore, text: str, situation: str) -> dict | None:
    """{intent, owner_said, jump_to, staff_name, task_title, task_repeat, task_kind} 또는 None (에이전트를 끔, 실패)."""
    if not config.agent_on("intent"):
        return None
    proposal = runner.run(SPEC, {"text": text, "situation": situation}, run_context(view))
    return proposal.content if proposal else None
