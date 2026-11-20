"""부서 팀장 LLM (에이전트 조직 개편 7단계, donna-voice/docs/agent-org-plan.md 7-1).

부서(customer 고객 응대, quality 매장 품질 관리, marketing 마케팅)마다 사원들이 낸 결과만 판단한다 (2026-11-20 결정).
할 수 있는 것: 결과마다 남길지(keep) 뺄지(drop)와 한 줄 이유, 사장님께 말할 순서, 부서 한 줄 요약.
할 수 없는 것: 글 고치기, 새 제안 만들기 (제출에 그런 칸이 없다. Harness/supervisor.py 와 같은 규칙).
실패하거나 끄면 None 이고, 부르는 쪽이 모두 남긴다 (사원 검사를 이미 통과했으므로).
밤(브리핑 준비)에 돌고, 영업 중 아쉬운 리뷰 알림처럼 사장님이 기다리는 길은 짧은 예산(realtime)으로 돈다.
"""

from Harness import runner
from Harness.grounding import Evidence
from Harness.spec import AgentSpec, Budget, RunContext, Tool
from Harness.tools import array, obj, string
from voice import config, width
from voice.agents import load_prompt
from voice.context import VoiceStore, run_context

DEPT_NAMES = {"customer": "고객 응대", "quality": "매장 품질 관리", "marketing": "마케팅"}
NIGHT = Budget(max_steps=3, max_rejections=2, max_seconds=30)
REALTIME = Budget(max_steps=2, max_rejections=1, max_seconds=15, strict=True)


def _submit(ids: list[str]) -> Tool:
    return Tool("submit_lead", "사원 결과마다 판단을 낸다", obj({
        "items": array(obj({"id": string("결과 id", enum=ids), "verdict": string("남길지 뺄지", enum=["keep", "drop"]),
                            "reason": string("한 줄 이유 (drop 이면 꼭)")}), "결과마다 하나씩"),
        "order": array(string("결과 id", enum=ids), "사장님께 말할 순서 (남긴 것만)"),
        "summary": string(f"부서 한 줄 요약 ({width.limit_note('tip')})"),
    }))


def user_message(task: dict, ctx: RunContext) -> str:
    rows = [f"- {i['id']} ({i['by']}): {i['text']}" for i in task["items"]]
    done = "\n".join(f"- {t}" for t in task.get("already") or []) or "(없음)"
    return (f"부서: {DEPT_NAMES[task['dept']]}\n오늘 사원들이 낸 결과:\n" + "\n".join(rows)
            + f"\n이미 알바생 화면에 있는 할 일:\n{done}\n결과마다 판단을 submit_lead 로 내 줘.")


def check(args: dict, evidence: Evidence, task: dict, ctx: RunContext, notes: list[str]) -> str | None:
    ids = [i["id"] for i in task["items"]]
    judged = [i.get("id") for i in args.get("items") or []]
    if sorted(judged) != sorted(ids):
        return f"결과마다 한 번씩 판단해 주세요: {', '.join(ids)}"
    for item in args["items"]:
        if item.get("verdict") == "drop" and not (item.get("reason") or "").strip():
            return f"{item['id']} 를 빼는 이유를 한 줄 적어 주세요"
    summary = (args.get("summary") or "").strip()
    if not width.fits(summary, "tip"):
        return width.too_long("summary", summary, "tip")
    return None


def review(view: VoiceStore, dept: str, items: list[dict], *, already: list[str] | None = None,
           realtime: bool = False) -> dict | None:
    """items: [{id, by, text}] → {verdicts: {id: {verdict, reason}}, order: [id], summary} 또는 None (끔, 실패)."""
    if not items or not config.agent_on("lead"):
        return None
    spec = AgentSpec(
        name=f"voice_team_lead_{dept}",
        system_prompt=lambda task, ctx: load_prompt("team_lead.txt", ctx.store).replace("{부서}", DEPT_NAMES[task["dept"]]),
        user_message=user_message,
        tools=[],
        submit=_submit([i["id"] for i in items]),
        check=check,
        task_id=lambda task: f"{task['dept']}:{'|'.join(i['id'] for i in task['items'])}",
        budget=REALTIME if realtime else NIGHT,
        temperature=0,
    )
    proposal = runner.run(spec, {"dept": dept, "items": items, "already": already or []}, run_context(view))
    if proposal is None or proposal.source != "AGENT":
        return None
    content = proposal.content
    verdicts = {i["id"]: {"verdict": i["verdict"], "reason": (i.get("reason") or "").strip()} for i in content["items"]}
    order = [i for i in content.get("order") or [] if verdicts.get(i, {}).get("verdict") == "keep"]
    return {"verdicts": verdicts, "order": order, "summary": (content.get("summary") or "").strip(), "run_id": proposal.run_id}
