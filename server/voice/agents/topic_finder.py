"""마케팅 소재 발굴 사원: 오늘 인스타에 올릴 메뉴와 이야기를 고른다 (에이전트 조직 개편 6-1, agent-org-plan.md).

손님이 좋아한 점(좋은 리뷰), 많이 나간 메뉴(포스 매출), 오늘 날씨를 보고 메뉴 1~3개와 한 줄 이야기(angle)를 고른다.
검사: 메뉴는 목록에 있고 사진이 있는 것만, 숫자는 도구 결과에 있는 것만, '인기' 같은 판매 주장은 매출을 조회했을 때만,
가격·할인·보상 금지 (1차 코드 감사 rules.topic_finder). 이야기에 고른 메뉴가 아닌 음식이 나오는지는 2차 LLM 감사
inspector.topic_finder (angle_menu).
실패하거나 끄면 None (지금처럼 이번 달 많이 나간 메뉴 3개를 쓴다). 감사 결과는 audit 으로 돌려주고 처리는 부르는 쪽이 정한다.
"""

from app.analysis.review.hcx_classifier import mask_personal_info
from Harness import runner
from Harness.spec import AgentSpec, Budget, RunContext, Tool
from Harness.tools import NO_ARGS, array, obj, string
from voice import config, notebook
from voice.agents import load_prompt
from voice import audit
from voice.audit import inspector, rules
from voice.audit import log as audit_log
from voice.agents.field_tasks import WEATHER
from voice.context import VoiceStore, run_context

TOP = "get_top_menus"


def _view(ctx: RunContext) -> VoiceStore:
    return ctx.snapshot  # type: ignore[return-value]


def top_menus(ctx: RunContext, task: dict, args: dict) -> dict:
    from voice.instagram import posts

    top = posts.top_menus(_view(ctx), 5)
    return {"period": top["period"], "items": [{"id": m["id"], "rank": m["rank"], "name": m["name"], "count": m["count_label"]}
                                               for m in top["items"]]}


def liked(ctx: RunContext, task: dict, args: dict) -> dict:
    from voice.jobs import briefing, strengths

    view = _view(ctx)
    recent = briefing.recent_positive(view, ctx.now)
    found = strengths.analyze(recent, view.menus, view.store.get("strengths"))
    texts = [mask_personal_info(r["text"]) for r in sorted(recent, key=lambda r: r["written_at"], reverse=True)[:5]]
    return {"liked": [{"label": t["label"], "count": t["count"]} for t in found["top"]], "reviews": texts}


def menus(ctx: RunContext, task: dict, args: dict) -> dict:
    return {"menus": [{"id": m["id"], "name": m["name"], "has_photo": bool(m.get("photo_url"))} for m in _view(ctx).menus]}


TOOLS = [Tool(TOP, "많이 나간 메뉴 순위 (포스 매출)", NO_ARGS, top_menus),
         Tool("get_liked", "최근 일주일 좋은 리뷰에서 손님이 좋아한 점과 리뷰 글", NO_ARGS, liked),
         Tool("get_menus", "메뉴 목록과 사진이 있는지", NO_ARGS, menus), WEATHER]
SUBMIT = Tool("submit_topic", "오늘 인스타 소재", obj({
    "menu_ids": array(string("메뉴 id"), "올릴 메뉴 1~3개 (사진 있는 것만)"),
    "angle": string("이 메뉴들을 어떤 이야기로 올릴지 한 줄"),
    "evidence": array(string("근거"), "어느 도구 결과의 무엇을 봤는지"),
}))


def user_message(task: dict, ctx: RunContext) -> str:
    return f"오늘: {ctx.now:%Y-%m-%d}\n오늘 인스타에 올리면 손님 반응이 좋을 메뉴와 이야기를 골라 submit_topic 으로 내 줘."


SPEC = AgentSpec(
    name="voice_topic_finder",
    system_prompt=lambda task, ctx: load_prompt("topic_finder.txt", ctx.store) + notebook.section(ctx.store_id, "marketing"),
    user_message=user_message,
    tools=TOOLS,
    submit=SUBMIT,
    check=rules.topic_finder,  # 1차 코드 감사 (감사팀)
    audit=inspector.topic_finder,  # 2차 LLM 감사 (감사팀)
    audit_returns=config.AUDIT_RETURNS,
    audit_seconds=config.AUDIT_ROUND_SECONDS,
    cache_scope=lambda task: audit.version(),
    task_id=lambda task: task["date"],
    budget=Budget(max_steps=5, max_rejections=2, max_seconds=40),
    temperature=0.4,
)


def suggest(view: VoiceStore) -> dict | None:
    """{menu_ids, angle, audit} 또는 None."""
    if not config.agent_on("topic"):
        return None
    day = view.now.date().isoformat()
    ctx = run_context(view)
    proposal = runner.run(SPEC, {"date": day}, ctx)
    audit_log.record_run(view.store_id, "instagram_post", f"topic:{day}", proposal, ctx.run_id)
    if proposal is None or proposal.source != "AGENT":
        return None
    return {"menu_ids": [str(i) for i in proposal.content["menu_ids"]], "angle": proposal.content["angle"].strip(),
            "audit": audit.brief(proposal.audit)}
