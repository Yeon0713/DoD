"""업무 수첩 규칙 판정 (인사과 4-8, donna-voice/docs/agent-structure.md 9장 7단계).

입력: 사장님 말(고침·반려 지시), 업무, 지금 규칙. 출력: 계속 지킬 규칙인지, 칸(담당 | 가게 공통), 규칙 한 줄, 덮을 옛 규칙,
코드로 볼 수 있는 것(금지 낱말, 이모티콘 금지). "이건 좀 더 부드럽게"처럼 그 건에만 하는 말은 규칙이 아니다.
검사: 규칙 글 폭(tip 한도), replaces 가 실제 규칙 id 인지. 예산 10초, strict 아님 (뒤 스레드에서 돌므로 사장님이 기다리지 않는다. 강제 제출·400 우회·429 기다리기가 돌게, known-bugs B8).
실패하거나 끄면 None (적지 않는다).
"""

from Harness import runner
from Harness.grounding import Evidence
from Harness.spec import AgentSpec, Budget, RunContext, Tool
from Harness.tools import array, obj, string
from voice import config, width
from voice.agents import load_prompt
from voice.context import VoiceStore, run_context


def boolean(description: str) -> dict:
    return {"type": "boolean", "description": description}


def _submit(ids: list[str]) -> Tool:
    return Tool("submit_rule", "사장님 말이 계속 지킬 규칙인지 낸다", obj({
        "is_rule": boolean("앞으로도 계속 지킬 규칙이면 true, 이 글에만 하는 말이면 false"),
        "scope": string("규칙이 이 업무에만 해당하면 agent, 가게의 모든 글에 해당하면 common", enum=["agent", "common"]),
        "text": string(f"규칙 한 줄, '~기' 꼴로 짧게 (예: 이모티콘 쓰지 않기). 규칙이 아니면 빈 글자 ({width.limit_note('tip')})"),
        "replaces": array(string("이 규칙과 부딪혀 덮을 옛 규칙 id", enum=ids or ["none"]), "덮을 옛 규칙 id. 없으면 빈 목록"),
        "banned_words": array(string("쓰면 안 되는 낱말 하나"), "규칙이 금지한 낱말 (코드로 검사). 없으면 빈 목록"),
        "no_emoji": boolean("이모티콘을 쓰지 말라는 규칙이면 true"),
    }))


def user_message(task: dict, ctx: RunContext) -> str:
    current = "\n".join(f"- {r['id']}: {r['text']}" for r in task["rules"]) or "(없음)"
    return (f"업무: {task['job']}\n사장님 말: \"{task['said']}\"\n지금 수첩 규칙:\n{current}\n"
            "submit_rule 로 내 줘.")


def check(args: dict, evidence: Evidence, task: dict, ctx: RunContext, notes: list[str]) -> str | None:
    text = (args.get("text") or "").strip()
    if args.get("is_rule") and not text:
        return "규칙이면 text 에 규칙 한 줄을 적어 주세요"
    if text and not width.fits(text, "tip"):
        return width.too_long("text", text, "tip")
    ids = {r["id"] for r in task["rules"]}
    # 'none': 수첩이 비면 스키마 enum 이 ["none"] 뿐이라 모델이 적는다. 덮을 규칙 없음으로 본다 (judge 도 걸러 낸다)
    unknown = [i for i in args.get("replaces") or [] if i != "none" and i not in ids]
    if unknown:
        return f"replaces 에는 지금 수첩 규칙 id 만 적을 수 있어요: {', '.join(unknown)}"
    return None


def judge(view: VoiceStore, said: str, job_name: str, rules: list[dict]) -> dict | None:
    """{is_rule, scope, text, replaces, banned_words, no_emoji} 또는 None (끔, 실패)."""
    if not config.agent_on("notebook"):
        return None
    spec = AgentSpec(
        name="voice_notebook_rule",
        system_prompt=lambda task, ctx: load_prompt("notebook_rule.txt", ctx.store),
        user_message=user_message,
        tools=[],
        submit=_submit([r["id"] for r in rules]),
        check=check,
        task_id=lambda task: f"{task['job']}:{task['said']}",
        budget=Budget(max_steps=2, max_rejections=2, max_seconds=10),  # 거절 한 번은 다시 내게
        temperature=0,
    )
    proposal = runner.run(spec, {"said": said, "job": job_name, "rules": rules}, run_context(view))
    if proposal is None or proposal.source != "AGENT":
        return None
    c = proposal.content
    # 모델은 replaces 의 enum ["none"] 을 따라 banned_words 에도 'none' 을 적는다 (금지 낱말이 아니다)
    banned = [str(w).strip() for w in c.get("banned_words") or [] if str(w).strip() and str(w).strip().lower() != "none"]
    return {"is_rule": bool(c.get("is_rule")), "scope": c.get("scope") or "agent", "text": (c.get("text") or "").strip(),
            "replaces": [i for i in c.get("replaces") or [] if i != "none"], "banned_words": banned,
            "no_emoji": bool(c.get("no_emoji"))}
