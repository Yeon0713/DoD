"""같은 할 일인지 묻는 좁은 질문 (에이전트 조직 개편 2단계, donna-voice/docs/agent-org-plan.md 2-2).

바이그램 겹침(similar.dice)으로 고른 후보가 있을 때만 부른다. 새 할 일이 후보 중 하나와 알바생에게 같은 행동을 시키는지 고른다.
예산: 1단계, 5초 (strict). 실패하거나 끄면 None (새로 넣는다. 겹침을 놓쳐도 할 일이 하나 더 뜰 뿐이고, 잘못 묶으면 교정이 사라진다).
"""

from Harness import runner
from Harness.grounding import Evidence
from Harness.spec import AgentSpec, Budget, RunContext, Tool
from Harness.tools import obj, string
from voice import config
from voice.agents import load_prompt
from voice.context import VoiceStore, run_context

NONE = "none"


def _submit(ids: list[str]) -> Tool:
    return Tool("submit_same", "같은 행동인 후보 id 를 낸다. 없으면 none",
                obj({"same_as": string("같은 행동인 후보 id 또는 none", enum=ids + [NONE]), "reason": string("한 줄 이유")}))


def user_message(task: dict, ctx: RunContext) -> str:
    lines = "\n".join(f"- {c['id']}: {c['text']}" for c in task["candidates"])
    return f"새 할 일: {task['new']}\n후보:\n{lines}\nsubmit_same 으로 내 줘."


def check(args: dict, evidence: Evidence, task: dict, ctx: RunContext, notes: list[str]) -> str | None:
    allowed = [c["id"] for c in task["candidates"]] + [NONE]
    return None if args.get("same_as") in allowed else f"same_as 는 다음 중 하나여야 해요: {', '.join(allowed)}"


def judge(view: VoiceStore, new: str, candidates: list[dict]) -> str | None:
    """candidates: [{id, text}]. 같은 행동인 후보 id 또는 None."""
    if not candidates or not config.agent_on("same"):
        return None
    spec = AgentSpec(
        name="voice_same_task",
        system_prompt=lambda task, ctx: load_prompt("same_task.txt", ctx.store),
        user_message=user_message,
        tools=[],
        submit=_submit([c["id"] for c in candidates]),
        check=check,
        task_id=lambda task: task["new"],
        budget=Budget(max_steps=1, max_rejections=1, max_seconds=5, strict=True),
        temperature=0,
    )
    proposal = runner.run(spec, {"new": new, "candidates": candidates}, run_context(view))
    found = proposal.content.get("same_as") if proposal else None
    return None if found in (None, NONE) else found
