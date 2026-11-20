"""부정 리뷰 사원: 아쉬운 리뷰에서 알바생 교정 할 일을 쓴다 (에이전트 조직 개편 3단계, donna-voice/docs/agent-org-plan.md 3-1).

원칙 한 줄(프롬프트): 이 가게 알바생이 다음 근무에서 행동을 바꿔 막을 수 있었던 문제인가? 아니면 actionable=false.
검사
  1. quote 가 리뷰에 글자 그대로 있다
  2. actionable=false 면 끝 (카드 없음. 애매하면 넣지 않는다)
  3. 제목·내용 폭 (width staff.title / staff.detail)
  4. 가격·할인·보상 약속 금지
  5. 알바생이 할 수 없는 일(사기·바꾸기·가격·정책)이 있는지 좁은 질문(quote_judge staff_scope). 묻지 못하면 템플릿으로 물러난다
배달 지연은 부르지 않는다 (cause.NO_CARD_YET, 주문 기록이 생길 때까지).
card_for 가 입구다: 규칙(cause.classify) 결과에서 카드만 에이전트 것으로 바꾼다. 실패하거나 끄면 규칙 템플릿 그대로.
"""

from app.analysis.review.hcx_classifier import mask_personal_info
from Harness import guards, runner
from Harness.agents import quote_judge
from Harness.grounding import Evidence
from Harness.spec import AgentSpec, Budget, RunContext, Tool
from Harness.tools import NO_ARGS, obj, string
from voice import config, notebook, staff, width
from voice.agents import load_prompt
from voice.agents.voice_reply import MENU_LIST
from voice.context import VoiceStore, run_context
from voice.jobs import cause

UNCHECKED = "검토 안 됨"


def _view(ctx: RunContext) -> VoiceStore:
    return ctx.snapshot  # type: ignore[return-value]


def manual(ctx: RunContext, task: dict, args: dict) -> dict:
    tasks = staff.store_tasks(ctx.store_id)
    return {"manual": [t["title"] for t in tasks if t["repeat"] == "daily" and not t["canceled"]],
            "recent": [t["title"] for t in tasks if t["repeat"] != "daily" and not t["canceled"]][-10:]}


MANUAL = Tool("get_staff_tasks", "알바생 매뉴얼(매일 할 일)과 최근에 넣은 할 일 제목", NO_ARGS, manual)
# title·detail 설명의 "actionable 이 false 면" 을 "알바생이 막을 수 없는 문제면" 으로 바꾸고 한도를 글자 수로 적었다 (2026-11-21).
# 실제 CLOVA 5번씩: 시연 리뷰 "국물이 다 새서 봉투가 흥건했어요"가 FFFFF → 카드 3번(나머지 2번은 실패해 템플릿 카드),
# 정답이 false 인 "양이 적어요"·"입맛에 안 맞아요"는 그대로 FFFFF. 대신 "면이 불어서 왔어요"는 TFTFT → FFFFF.
# 판정 칸을 맨 뒤로 옮기면 "양이 적어요"에도 카드를 내서(5번 중 2번) 맨 앞에 둔다.
SUBMIT = Tool("submit_fix_card", "알바생 교정 할 일을 낸다", obj({
    "actionable": {"type": "boolean", "description": "알바생이 다음 근무에서 행동을 바꿔 막을 수 있었던 문제면 true"},
    "quote": string("판단 근거가 된 리뷰 속 말을 글자 그대로"),
    "title": string(f"알바생 화면에 보일 짧은 제목 ({width.limit_note('staff.title')}). 알바생이 막을 수 없는 문제면 빈 글자"),
    "detail": string(f"무엇을 어떻게 하는지 한 문장 ({width.limit_note('staff.detail')}). 알바생이 막을 수 없는 문제면 빈 글자"),
}, required=["actionable", "quote", "title", "detail"]))


def user_message(task: dict, ctx: RunContext) -> str:
    review = _view(ctx).review(task["review_id"]) or {}
    return (f'아쉬운 리뷰 (별점 {review.get("rating")}): "{mask_personal_info(review.get("text", ""))}"\n'
            "알바생 교정 할 일을 submit_fix_card 로 내 줘.")


def check(args: dict, evidence: Evidence, task: dict, ctx: RunContext, notes: list[str]) -> str | None:
    review = _view(ctx).review(task["review_id"]) or {}
    original = mask_personal_info(review.get("text", ""))
    quote = (args.get("quote") or "").strip()
    if not quote or quote not in original:
        return f'quote 는 리뷰 "{original}" 에서 글자 그대로 옮겨 주세요'
    if args.get("actionable") is not True:
        return None
    title, detail = (args.get("title") or "").strip(), (args.get("detail") or "").strip()
    if not title or not detail:
        return "actionable 이 true 면 title 과 detail 을 채워 주세요"
    if not width.fits(title, "staff.title"):
        return width.too_long("title", title, "staff.title")
    if not width.fits(detail, "staff.detail"):
        return width.too_long("detail", detail, "staff.detail")
    reason = guards.first(guards.price_or_discount(f"{title} {detail}"), guards.promise(f"{title} {detail}"))
    if reason:
        return reason
    outside = quote_judge.ask("staff_scope", f"{title}. {detail}", ctx, review_text=original)
    if outside is None:
        notes.append(UNCHECKED)
        return None
    if outside:
        return f"알바생이 지금 있는 것으로 할 수 없는 일이 있어요: {', '.join(outside)}. 알바생이 할 수 있는 일만 써 주세요"
    return None


SPEC = AgentSpec(
    name="voice_fix_card",
    system_prompt=lambda task, ctx: load_prompt("fix_card.txt", ctx.store) + notebook.section(ctx.store_id, "negative_review"),
    user_message=user_message,
    tools=[MENU_LIST, MANUAL],
    submit=SUBMIT,
    check=check,
    task_id=lambda task: task["review_id"],
    budget=Budget(max_steps=4, max_rejections=2, max_seconds=30),
    temperature=0.3,
)


def suggest(view: VoiceStore, review: dict) -> dict | None:
    """{actionable, quote, title, detail} 또는 None (끔, 실패, 검토 못 함)."""
    if not config.agent_on("fixcard"):
        return None
    proposal = runner.run(SPEC, {"review_id": review["id"]}, run_context(view))
    if proposal is None or proposal.source != "AGENT" or UNCHECKED in proposal.notes:
        return None
    c = proposal.content
    return {"actionable": c.get("actionable") is True, "quote": c["quote"].strip(),
            "title": (c.get("title") or "").strip(), "detail": (c.get("detail") or "").strip()}


def card_for(view: VoiceStore, review: dict) -> dict:
    """cause.classify 결과 + card_source(AGENT | TEMPLATE | NONE). 에이전트 카드면 reply 는 조치 없는 사과(plain)이고,
    답글은 부르는 쪽이 voice_reply.write(fix=...) 로 같은 조치를 담아 쓴다."""
    found = cause.classify(review)
    if found["detail"] in cause.NO_CARD_YET:
        return {**found, "card_source": "NONE"}
    agent = suggest(view, review)
    if agent is None:
        return {**found, "card_source": "TEMPLATE" if found["card"] else "NONE"}
    if not agent["actionable"]:
        return {**found, "card": None, "reply": found["plain"], "card_source": "NONE", "quote": agent["quote"]}
    return {**found, "card": {"title": agent["title"], "detail": agent["detail"]}, "reply": found["plain"],
            "card_source": "AGENT", "quote": agent["quote"]}
