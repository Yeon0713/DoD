"""F3·F6 답글 에이전트.

task 키
  kind       "AUTO"(F3 아쉬운 리뷰에 바로 답하기) | "SCHEDULED"(F6 좋은 리뷰 예약 답글) | "DRAFT"(허락 거절 때 초안)
  review_id  답글을 달 리뷰
  occasion   F6: {kind, label, explanation, post_at} 올릴 때와 이유

검사는 감사팀이 한다 (voice/audit/, 감사팀 계획)
  1. 1차 코드 감사 rules.reply: 길이, 빈칸, 메뉴·사실 메모 대조, quoted_review_words 가 리뷰에 글자 그대로 있는지, 가격·할인 지어내기
  2. 2차 LLM 감사 inspector.reply: reply_critic.inspect (보상, 고칠 점, 지어낸 사정, 변명, 아는 척, 리뷰와 상관없는 말).
     불합격이면 같은 대화로 지적을 돌려준다 (최대 2번). 검토를 부를 수 없으면 '검토 안 됨'을 남기고 금지어 정규식으로 대신 거른다
물러나기: 주제·이유별 안전 템플릿 (template). 에이전트를 끈 때도 템플릿을 쓴다.
"""

from app.analysis.review.hcx_classifier import mask_personal_info
from app.review_reply_writer import write_reply_with_clova as writer
from app.review_reply_writer.write_reply_with_clova import clean_answer
from Harness import guards, runner
from Harness.agents.reply_agent import SUBMIT
from Harness.spec import AgentSpec, Budget, RunContext, Tool
from Harness.tools import NO_ARGS
from voice import config, notebook, speech
from voice import audit
from voice.audit import inspector, rules
from voice.audit import log as audit_log
from voice.agents import load_prompt
from voice.clock import parse
from voice.context import VoiceStore, run_context

TOPIC_NAMES = {"delivery": "배달", "taste": "맛", "portion": "양", "service": "응대", "hygiene": "위생", "other": "기타"}
NEGATIVE_TEMPLATES = {
    "delivery": "늦은 배달로 불편을 드려 죄송합니다. 다음 주문은 더 빨리, 따뜻하게 보내 드릴게요.",
    "taste": "맛이 아쉬우셨다니 죄송합니다. 간과 조리 상태를 한 번 더 확인하겠습니다.",
    "portion": "양이 아쉬우셨다니 죄송합니다. 담는 양을 다시 살펴보겠습니다.",
    "service": "응대가 불편하셨다니 죄송합니다. 다음에는 더 세심하게 챙기겠습니다.",
    "hygiene": "불쾌하게 해 드려 정말 죄송합니다. 조리 공간 위생을 바로 다시 점검하겠습니다.",
    "other": "아쉬운 점을 남겨 주셔서 감사합니다. 말씀해 주신 부분을 꼭 살펴보겠습니다.",
}
POSITIVE_TEMPLATES = {
    "weather": "좋게 봐 주셔서 감사해요! 비 오는 날엔 따뜻한 {soup}도 잘 어울려요. 또 들러 주세요.",
    "game": "맛있게 드셔 주셔서 감사해요! 경기 보기 전에 든든하게 드시고 가세요.",
    "event": "좋은 리뷰 감사해요! {label} 가시는 길에 편하게 들러 주세요.",
    "season": "좋게 봐 주셔서 감사해요! 날이 추워졌는데 따뜻한 {soup}로 몸 녹이고 가세요.",
    "weekend": "좋은 리뷰 남겨 주셔서 감사해요! 주말에도 맛있게 준비해 둘게요.",
    "lunch": "맛있게 드셔 주셔서 감사해요! 점심 한 그릇 든든하게 드시러 또 들러 주세요.",
    "dinner": "맛있게 드셔 주셔서 감사해요! 저녁 한 끼 든든하게 드시러 또 들러 주세요.",
}


# ── 템플릿 (물러나기) ──


def _soup(view: VoiceStore) -> str:
    from voice.jobs.strengths import SOUP_RE

    return view.store.get("rain_menu") or next((m["name"] for m in view.menus if SOUP_RE.search(m["name"])), "국물 요리")


def template(view: VoiceStore, review: dict, occasion: dict | None, fix: dict | None = None) -> str:
    if review.get("sentiment") == "negative":
        if fix and fix.get("reply"):  # 원인을 안 아쉬운 리뷰: 원인과 실제로 할 조치를 적은 사과 (jobs/cause.py)
            return fix["reply"]
        return NEGATIVE_TEMPLATES[review.get("topic") or "other"]
    occasion = occasion or {}
    kind = occasion.get("template") or occasion.get("kind", "weekend")
    if kind not in POSITIVE_TEMPLATES:
        kind = "weekend"
    label = (occasion.get("context") or {}).get("event") or occasion.get("label", "")
    return POSITIVE_TEMPLATES[kind].format(soup=_soup(view), label=label)


# ── 도구 ──


def _view(ctx: RunContext) -> VoiceStore:
    return ctx.snapshot  # type: ignore[return-value]


def menu_list(ctx: RunContext, task: dict, args: dict) -> list[dict]:
    return [{"name": m["name"], "price": m.get("price")} for m in _view(ctx).menus]


def store_facts(ctx: RunContext, task: dict, args: dict) -> dict:
    if not ctx.store_facts:
        return {"facts": [], "note": "등록된 가게 사실이 없어요. 가게 사정(재료, 조리법, 직원 등)은 쓰지 마세요."}
    return {"facts": ctx.store_facts, "note": "이 목록에 있는 사실만 글자 그대로 쓸 수 있어요."}


def reply_occasion(ctx: RunContext, task: dict, args: dict) -> dict:
    occasion = task.get("occasion")
    if not occasion:
        return {"note": "바로 올리는 답글이에요. 정해진 상황은 없어요."}
    post_at = parse(occasion["post_at"])
    context = occasion.get("context") or {}
    that_day = [line for line in (
        "그날 비 소식이 있어요" if context.get("rain") else None,
        "그날 날이 추워요" if context.get("cold") else None,
        f"그날 {context['event']}가 열려요" if context.get("event") else None,
        f"그날 {context['game']} 경기가 있어요" if context.get("game") else None,
    ) if line]
    return {"kind": occasion["kind"], "label": occasion["label"], "why": occasion["explanation"],
            "post_day": f"{speech.weekday(post_at.date())}요일", "that_day": that_day or ["그날 특별한 일은 없어요"]}


MENU_LIST = Tool("get_menu_list", "우리 가게 메뉴 이름과 가격", NO_ARGS, menu_list)
STORE_FACTS = Tool("get_store_facts", "가게가 직접 등록한 사실 메모. 여기 있는 사실만 글에 쓸 수 있다", NO_ARGS, store_facts)
REPLY_OCCASION = Tool("get_reply_occasion", "이 답글을 언제, 왜 올리는지와 올리는 날의 날씨·행사·경기", NO_ARGS, reply_occasion)


# ── 프롬프트 ──


def notebook_agent(task: dict, ctx: RunContext) -> str:
    """업무 수첩 칸: 아쉬운 리뷰면 부정 리뷰 담당, 아니면 재방문 유도 담당 (voice/hr.py JOBS)."""
    review = _view(ctx).review(task["review_id"]) or {}
    return "negative_review" if review.get("sentiment") == "negative" else "revisit"


def system_prompt(task: dict, ctx: RunContext) -> str:
    base = writer.load_prompt("review_reply_prompt.txt", ctx.store)  # 팀이 다듬어 온 답글 말투 프롬프트를 그대로 쓴다
    return f"{base}\n\n{load_prompt('voice_reply.txt', ctx.store)}{notebook.section(ctx.store_id, notebook_agent(task, ctx))}"


def user_message(task: dict, ctx: RunContext) -> str:
    review = _view(ctx).review(task["review_id"]) or {}
    rows = [
        f"오늘: {ctx.now:%Y-%m-%d}",
        "리뷰 정보",
        "- 손님 구분: 일반 손님",
        f"- 별점: {review.get('rating')}",
        f"- 리뷰 분위기: {'아쉬움' if review.get('sentiment') == 'negative' else '좋음'}",
        f"- 리뷰 주제: {TOPIC_NAMES.get(review.get('topic') or 'other')}",
        f'- 리뷰 글: "{mask_personal_info(review.get("text", ""))}"',
    ]
    if task.get("occasion"):
        rows.append(f"\n이 답글은 정해진 때에 올려요: {task['occasion']['explanation']}. get_reply_occasion 으로 확인할 수 있어요.")
    if task.get("fix"):
        rows.append(f"\n원인: {task['fix']['cause']}. 가게가 오늘부터 할 조치: {task['fix']['action']}. "
                    "사과와 함께 이 조치를 한 문장으로 적어. 보상은 쓰지 마 (보상 문장은 사장님이 정한 것을 따로 붙여).")
    if task.get("revise"):  # 사장님 고침 지시 (인사과 6단계). 지시에 보상 말이 있어도 보상은 쓰지 않는다 (코드가 붙인다)
        rows.append(f'\n지난 답글: "{task["revise"]["previous"]}"\n사장님 고침 지시: "{task["revise"]["instruction"]}"\n'
                    "지난 답글을 이 지시대로 고쳐 써. 지시에 없는 것은 바꾸지 마. 보상·할인은 지시에 있어도 쓰지 마.")
    return "\n".join(rows)


def finalize(args: dict, task: dict, ctx: RunContext) -> dict:
    return {"text": clean_answer(str(args.get("text") or ""))}


def fallback(task: dict, ctx: RunContext) -> dict:
    view = _view(ctx)
    return {"text": template(view, view.review(task["review_id"]) or {}, task.get("occasion"), task.get("fix"))}


SPEC = AgentSpec(
    name="voice_reply",
    system_prompt=system_prompt,
    user_message=user_message,
    tools=[MENU_LIST, STORE_FACTS, REPLY_OCCASION],
    submit=SUBMIT,
    check=rules.reply,  # 1차 코드 감사 (감사팀)
    audit=inspector.reply,  # 2차 LLM 감사 (감사팀)
    audit_returns=config.AUDIT_RETURNS,
    audit_seconds=config.AUDIT_ROUND_SECONDS,
    cache_scope=lambda task: audit.version(),  # 감사 기준이 바뀌면 예전 결과를 다시 쓰지 않는다
    task_id=lambda task: f"{task['kind']}:{task['review_id']}" + (":revise" if task.get("revise") else ""),
    fallback=fallback,
    finalize=finalize,
    budget=Budget(max_steps=5, max_rejections=2, max_seconds=40),
    temperature=0.5,
)


def _run(view: VoiceStore, review: dict, task: dict):
    """담당을 돌리고 이번에 새로 감사한 회차를 감사 기록에 남긴다."""
    ctx = run_context(view)
    proposal = runner.run(SPEC, task, ctx)
    audit_log.record_run(view.store_id, inspector.reply_job(review), review["id"], proposal, ctx.run_id)
    return proposal


def _notes(proposal) -> list[str]:
    unchecked = proposal.audit is not None and proposal.audit["passed"] is None and rules.UNCHECKED not in proposal.notes
    return [*proposal.notes, rules.UNCHECKED] if unchecked else list(proposal.notes)


def revise(view: VoiceStore, review: dict, kind: str, previous: str, instruction: str, occasion: dict | None = None,
           fix: dict | None = None) -> dict | None:
    """사장님 고침 지시대로 다시 쓴 답글 {text, source, notes, audit}. 에이전트가 끄였거나 실패하거나 감사를 끝내 통과하지 못하면 None
    (템플릿으로 바꾸면 지시를 무시하게 되므로). 검사는 처음 쓸 때와 같다. 고침 지시는 critic 의 owner_instruction 으로 넘기지 않는다."""
    if not config.agent_on("reply"):
        return None
    task = {"kind": kind, "review_id": review["id"], "occasion": occasion, "fix": fix,
            "revise": {"previous": previous, "instruction": instruction}}
    proposal = _run(view, review, task)
    if proposal is None or proposal.source != "AGENT" or (proposal.audit or {}).get("passed") is False:
        return None
    return {"text": proposal.content["text"], "source": "AGENT", "notes": _notes(proposal), "audit": audit.brief(proposal.audit)}


def write(view: VoiceStore, review: dict, kind: str, occasion: dict | None = None, fix: dict | None = None) -> dict:
    """답글 하나 → {text, source(AGENT|FALLBACK|TEMPLATE), notes, audit}. 언제나 글이 나온다.
    audit 은 감사 결과 (Proposal.audit, 템플릿이면 None). 끝내 불합격(passed False)이면 걸린 글 그대로 돌려주고, 처리는 부르는 쪽이
    audit.settle 로 정한다 (보류·템플릿).
    fix: 원인을 안 아쉬운 리뷰 {cause, action, reply} (jobs/cause.py). 에이전트에게 조치를 알려 주고, 템플릿은 reply 를 쓴다."""
    if not config.agent_on("reply"):
        return {"text": template(view, review, occasion, fix), "source": "TEMPLATE", "notes": [], "audit": None}
    task = {"kind": kind, "review_id": review["id"], "occasion": occasion, "fix": fix}
    proposal = _run(view, review, task)
    if proposal is None:
        return {"text": template(view, review, occasion, fix), "source": "TEMPLATE", "notes": [], "audit": None}
    return {"text": proposal.content["text"], "source": proposal.source, "notes": _notes(proposal), "audit": audit.brief(proposal.audit)}


# ── 사장님이 정한 보상 문장 (2026-11-18) ──
# 보상 문장은 LLM 에 주지 않고 코드가 붙인다. reply_critic.owner_gives() 는 지시문에 보상 말투가 있으면 답글의 보상 문장을
# 모두 허락하므로(Harness/agents/reply_critic.py), 프리셋을 owner_instruction 으로 넘기면 LLM 이 지어낸 "환불"까지 통과한다.


def compose(base: str, preset: str | None) -> str:
    """사과 글 뒤에 사장님이 정한 보상 문장을 그대로 붙인다."""
    return f"{base.rstrip()} {preset.strip()}" if preset else base.strip()


def safe_reply(text: str, allowed: str | None, fallback: str) -> tuple[str, list[str]]:
    """올리기 직전 검사: 사장님이 정한 문장(allowed)을 뺀 나머지에 보상·가격 말이 있으면 fallback(템플릿 사과)으로 바꾼다.
    → (올릴 글, 남길 메모)"""
    rest = text.replace(allowed, " ") if allowed else text
    if guards.promise_hit(rest) or guards.PRICE_RE.search(rest):
        return compose(fallback, allowed), ["보상 문장 걸러냄"]
    return text, []
