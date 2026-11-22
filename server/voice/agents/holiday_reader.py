"""네이버 플레이스 휴무 안내에서 쉬는 날짜 뽑기 (에이전트 조직 개편 6-3).

입력은 가게를 등록할 때 저장해 둔 휴무 안내(closed_note)와 최근 소식 글이다. 날짜를 적은 문장이 없으면 빈 목록.
검사: 날짜가 YYYY-MM-DD 이고 오늘부터 60일 안, quote 가 입력 글에 글자 그대로 있다.
뽑은 날은 확정하지 않는다. 아침 브리핑에서 사장님께 묻는다 (voice/holidays.py).
인용이 그 날 쉰다는 뜻인지는 2차 LLM 감사 inspector.holiday_reader 가 본다. 끝내 불합격하면 빈 목록처럼 None (결정 7).
"""

from Harness import runner
from Harness.spec import AgentSpec, Budget, RunContext, Tool
from Harness.tools import array, obj, string
from voice import config
from voice.agents import load_prompt
from voice import audit
from voice.audit import inspector, rules
from voice.audit import log as audit_log
from voice.context import VoiceStore, run_context

ITEM = obj({"date": string("쉬는 날 YYYY-MM-DD"), "quote": string("그 날짜를 적은 부분을 입력 글에서 글자 그대로")})
SUBMIT = Tool("submit_holidays", "글에 적힌 쉬는 날 (없으면 빈 목록)", obj({"items": array(ITEM, "쉬는 날 목록")}))


def user_message(task: dict, ctx: RunContext) -> str:
    texts = "\n".join(f"- {t}" for t in task["texts"])
    return f"오늘: {ctx.now:%Y-%m-%d} ({'월화수목금토일'[ctx.now.weekday()]}요일)\n네이버 플레이스 글:\n{texts}\n쉬는 날을 submit_holidays 로 내 줘."


SPEC = AgentSpec(
    name="voice_holiday_reader",
    system_prompt=lambda task, ctx: load_prompt("holiday_reader.txt", ctx.store),
    user_message=user_message,
    tools=[],
    submit=SUBMIT,
    check=rules.holiday_reader,  # 1차 코드 감사 (감사팀)
    audit=inspector.holiday_reader,  # 2차 LLM 감사 (감사팀)
    audit_returns=config.AUDIT_RETURNS,
    audit_seconds=config.AUDIT_ROUND_SECONDS,
    cache_scope=lambda task: audit.version(),
    task_id=lambda task: "|".join(task["texts"]),
    budget=Budget(max_steps=2, max_rejections=1, max_seconds=20),
    temperature=0,
)


def suggest(view: VoiceStore, texts: list[str]) -> list[dict] | None:
    """[{date, quote}] 또는 None (끔, 실패, 감사를 끝내 통과하지 못함·감사 못 함)."""
    if not config.agent_on("holiday"):
        return None
    ctx = run_context(view)
    proposal = runner.run(SPEC, {"texts": texts}, ctx)
    audit_log.record_run(view.store_id, "holiday", f"holiday:{view.now.date().isoformat()}", proposal, ctx.run_id)
    if proposal is None or proposal.source != "AGENT" or audit.settle(view.store_id, "holiday", proposal.audit) != "ok":
        return None
    return [{"date": str(i["date"]), "quote": i["quote"].strip()} for i in proposal.content.get("items") or []]
