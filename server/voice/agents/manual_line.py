"""매뉴얼 한 줄 다듬기 (에이전트 조직 개편 2단계, 매뉴얼 코칭 사원. donna-voice/docs/agent-org-plan.md 2-4).

일주일에 세 번 같은 할 일이 나오면 매일 할 일(매뉴얼)로 올리자고 제안한다. 그 한 줄을 여기서 다듬는다.
묶음 안 할 일에 없는 행동을 더하지 않는다. 실패하거나 끄면 None (부르는 쪽이 첫 할 일 제목을 그대로 쓴다).
"""

from Harness import guards, runner
from Harness.grounding import Evidence
from Harness.spec import AgentSpec, Budget, RunContext, Tool
from Harness.tools import obj, string
from voice import config, notebook, width
from voice.agents import load_prompt
from voice.context import VoiceStore, run_context
from voice.similar import dice

MIN_OVERLAP = 0.2  # 다듬은 글이 묶음 안 할 일 하나와는 이만큼 겹쳐야 한다 (없는 행동을 지어내지 않게)

SUBMIT = Tool("submit_manual", "매일 할 일 한 줄을 낸다",
              obj({"title": string("알바생 화면에 보일 짧은 제목"), "detail": string("무엇을 어떻게 하는지 한 문장")}))


def user_message(task: dict, ctx: RunContext) -> str:
    items = "\n".join(f"- {t}" for t in task["items"])
    manual = "\n".join(f"- {t}" for t in task["manual"]) or "(없음)"
    return f"일주일 동안 반복해서 넣은 할 일:\n{items}\n지금 매뉴얼:\n{manual}\n매일 할 일 한 줄로 다듬어 submit_manual 로 내 줘."


def check(args: dict, evidence: Evidence, task: dict, ctx: RunContext, notes: list[str]) -> str | None:
    title, detail = (args.get("title") or "").strip(), (args.get("detail") or "").strip()
    if not title or not detail:
        return "title 과 detail 을 모두 채워 주세요"
    if not width.fits(title, "staff.title"):
        return f"title 이 길어요 (폭 {width.width(title)} > {width.LIMITS['staff.title']}). 더 짧게 줄여 주세요"
    if not width.fits(detail, "staff.detail"):
        return f"detail 이 길어요 (폭 {width.width(detail)} > {width.LIMITS['staff.detail']}). 한 문장으로 줄여 주세요"
    reason = guards.first(guards.price_or_discount(f"{title} {detail}"), guards.promise(f"{title} {detail}"))
    if reason:
        return reason
    if max(dice(f"{title} {detail}", item) for item in task["items"]) < MIN_OVERLAP:
        return "반복해서 넣은 할 일에 있는 행동만 써 주세요. 새 행동을 더하지 마세요"
    return None


SPEC = AgentSpec(
    name="voice_manual_line",
    system_prompt=lambda task, ctx: load_prompt("manual_line.txt", ctx.store) + notebook.section(ctx.store_id, "manual_coach"),
    user_message=user_message,
    tools=[],
    submit=SUBMIT,
    check=check,
    task_id=lambda task: "|".join(task["items"]),
    budget=Budget(max_steps=3, max_rejections=2, max_seconds=20),
    temperature=0.2,
)


def write(view: VoiceStore, items: list[str], manual: list[str]) -> dict | None:
    """{title, detail} 또는 None."""
    if not config.agent_on("manual"):
        return None
    proposal = runner.run(SPEC, {"items": items, "manual": manual}, run_context(view))
    return {"title": proposal.content["title"].strip(), "detail": proposal.content["detail"].strip()} if proposal else None
