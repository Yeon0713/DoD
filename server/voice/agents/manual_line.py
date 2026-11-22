"""매뉴얼 한 줄 다듬기 (에이전트 조직 개편 2단계, 매뉴얼 코칭 사원. donna-voice/docs/agent-org-plan.md 2-4).

일주일에 세 번 같은 할 일이 나오면 매일 할 일(매뉴얼)로 올리자고 제안한다. 그 한 줄을 여기서 다듬는다.
묶음 안 할 일에 없는 행동을 더하지 않는다 (1차 코드 감사 rules.manual_line 의 겹침, 2차 LLM 감사 inspector.manual_line 의 manual_added).
실패하거나 끄거나 감사를 끝내 통과하지 못하면 None (부르는 쪽이 첫 할 일 제목을 그대로 쓴다, 결정 7).
"""

from Harness import runner
from Harness.spec import AgentSpec, Budget, RunContext, Tool
from Harness.tools import obj, string
from voice import config, notebook
from voice.agents import load_prompt
from voice import audit
from voice.audit import inspector, rules
from voice.audit import log as audit_log
from voice.context import VoiceStore, run_context

SUBMIT = Tool("submit_manual", "매일 할 일 한 줄을 낸다",
              obj({"title": string("알바생 화면에 보일 짧은 제목"), "detail": string("무엇을 어떻게 하는지 한 문장")}))


def user_message(task: dict, ctx: RunContext) -> str:
    items = "\n".join(f"- {t}" for t in task["items"])
    manual = "\n".join(f"- {t}" for t in task["manual"]) or "(없음)"
    return f"일주일 동안 반복해서 넣은 할 일:\n{items}\n지금 매뉴얼:\n{manual}\n매일 할 일 한 줄로 다듬어 submit_manual 로 내 줘."


SPEC = AgentSpec(
    name="voice_manual_line",
    system_prompt=lambda task, ctx: load_prompt("manual_line.txt", ctx.store) + notebook.section(ctx.store_id, "manual_coach"),
    user_message=user_message,
    tools=[],
    submit=SUBMIT,
    check=rules.manual_line,  # 1차 코드 감사 (감사팀)
    audit=inspector.manual_line,  # 2차 LLM 감사 (감사팀)
    audit_returns=config.AUDIT_RETURNS,
    audit_seconds=config.AUDIT_ROUND_SECONDS,
    cache_scope=lambda task: audit.version(),
    task_id=lambda task: "|".join(task["items"]),
    budget=Budget(max_steps=3, max_rejections=2, max_seconds=20),
    temperature=0.2,
)


def write(view: VoiceStore, items: list[str], manual: list[str]) -> dict | None:
    """{title, detail} 또는 None."""
    if not config.agent_on("manual"):
        return None
    ctx = run_context(view)
    proposal = runner.run(SPEC, {"items": items, "manual": manual}, ctx)
    audit_log.record_run(view.store_id, "manual_task", "manual:" + "|".join(items), proposal, ctx.run_id)
    if proposal is None or audit.settle(view.store_id, "manual_task", proposal.audit) != "ok":
        return None
    return {"title": proposal.content["title"].strip(), "detail": proposal.content["detail"].strip()}
