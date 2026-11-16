"""F3·F6 답글 에이전트.

task 키
  kind       "AUTO"(F3 아쉬운 리뷰에 바로 답하기) | "SCHEDULED"(F6 좋은 리뷰 예약 답글) | "DRAFT"(허락 거절 때 초안)
  review_id  답글을 달 리뷰
  occasion   F6: {kind, label, explanation, post_at} 올릴 때와 이유

검사 순서 (Harness 리뷰 응대 에이전트와 같다)
  1. 코드 검사: 길이, 빈칸, 메뉴·사실 메모 대조, quoted_review_words 가 리뷰에 글자 그대로 있는지, 가격·할인 지어내기
  2. LLM 검토 Harness.agents.reply_critic.inspect (보상, 고칠 점, 지어낸 사정, 변명, 아는 척, 리뷰와 상관없는 말)
     검토를 부를 수 없으면 '검토 안 됨'을 남기고 금지어 정규식으로 대신 거른다
물러나기: 주제·이유별 안전 템플릿 (template). 에이전트를 끈 때도 템플릿을 쓴다.
"""

from app.analysis.review.hcx_classifier import mask_personal_info
from app.review_reply_writer import write_reply_with_clova as writer
from app.review_reply_writer.write_reply_with_clova import MAX_LENGTH, MIN_LENGTH, clean_answer
from Harness import guards, runner
from Harness.agents import reply_critic
from Harness.agents.reply_agent import SUBMIT
from Harness.grounding import Evidence
from Harness.spec import AgentSpec, Budget, RunContext, Tool
from Harness.tools import NO_ARGS
from voice import config, speech
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
}


# ── 템플릿 (물러나기) ──


def _soup(view: VoiceStore) -> str:
    from voice.jobs.strengths import SOUP_RE

    return view.store.get("rain_menu") or next((m["name"] for m in view.menus if SOUP_RE.search(m["name"])), "국물 요리")


def template(view: VoiceStore, review: dict, occasion: dict | None) -> str:
    if review.get("sentiment") == "negative":
        return NEGATIVE_TEMPLATES[review.get("topic") or "other"]
    kind = (occasion or {}).get("kind", "weekend")
    return POSITIVE_TEMPLATES[kind].format(soup=_soup(view), label=(occasion or {}).get("label", ""))


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
    return {"kind": occasion["kind"], "label": occasion["label"], "why": occasion["explanation"],
            "post_day": f"{speech.weekday(post_at.date())}요일"}


MENU_LIST = Tool("get_menu_list", "우리 가게 메뉴 이름과 가격", NO_ARGS, menu_list)
STORE_FACTS = Tool("get_store_facts", "가게가 직접 등록한 사실 메모. 여기 있는 사실만 글에 쓸 수 있다", NO_ARGS, store_facts)
REPLY_OCCASION = Tool("get_reply_occasion", "이 답글을 언제, 왜 올리는지 (비 소식, 경기, 행사, 주말, 추위)", NO_ARGS, reply_occasion)


# ── 프롬프트 ──


def system_prompt(task: dict, ctx: RunContext) -> str:
    base = writer.load_prompt("review_reply_prompt.txt", ctx.store)  # 팀이 다듬어 온 답글 말투 프롬프트를 그대로 쓴다
    return f"{base}\n\n{load_prompt('voice_reply.txt', ctx.store)}"


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
    return "\n".join(rows)


# ── 검사 ──


def _texts(args: dict, key: str) -> list[str]:
    value = args.get(key) or []
    return [str(v).strip() for v in value if str(v).strip()] if isinstance(value, list) else []


def check(args: dict, evidence: Evidence, task: dict, ctx: RunContext, notes: list[str]) -> str | None:
    view = _view(ctx)
    review = view.review(task["review_id"]) or {}
    text = clean_answer(str(args.get("text") or ""))
    quoted, menus, facts = _texts(args, "quoted_review_words"), _texts(args, "menus_mentioned"), _texts(args, "facts_used")
    reason = guards.first(
        guards.length(text, MIN_LENGTH, MAX_LENGTH, "답글"),
        guards.placeholder(text),
        guards.price_or_discount(text),
        guards.not_in(menus, [m["name"] for m in view.menus], "메뉴 이름"),
        guards.not_in(facts, ctx.store_facts, "가게 사실(get_store_facts 에 있는 문장만 쓸 수 있어요)"),
    )
    if reason:
        return reason
    if not quoted:
        return "quoted_review_words 에 답글이 대답한 리뷰 속 말을 1개 이상 적어 주세요"
    original = review.get("text", "")
    missing = [q for q in quoted if q not in original]
    if missing:
        return (f"quoted_review_words 의 {', '.join(repr(q) for q in missing)} 는 리뷰에 글자 그대로 없어요. "
                f'리뷰 원문 "{mask_personal_info(original)}" 에서 그대로 옮겨 주세요. 답글(text)은 바꾸지 않아도 돼요')
    verdict = reply_critic.inspect(
        text, ctx, review_text=mask_personal_info(original), has_complaint=review.get("sentiment") == "negative",
    )
    if verdict is None:
        notes.append("검토 안 됨")
        return guards.first(guards.memory(text), None if any(f in text for f in facts) else guards.made_up_fact(text))
    if not verdict.ok:
        return "검토에서 걸렸어요: " + "; ".join(v.describe() for v in verdict.violations)
    return None


def finalize(args: dict, task: dict, ctx: RunContext) -> dict:
    return {"text": clean_answer(str(args.get("text") or ""))}


def fallback(task: dict, ctx: RunContext) -> dict:
    view = _view(ctx)
    return {"text": template(view, view.review(task["review_id"]) or {}, task.get("occasion"))}


SPEC = AgentSpec(
    name="voice_reply",
    system_prompt=system_prompt,
    user_message=user_message,
    tools=[MENU_LIST, STORE_FACTS, REPLY_OCCASION],
    submit=SUBMIT,
    check=check,
    task_id=lambda task: f"{task['kind']}:{task['review_id']}",
    fallback=fallback,
    finalize=finalize,
    budget=Budget(max_steps=5, max_rejections=2, max_seconds=40),
    temperature=0.5,
)


def write(view: VoiceStore, review: dict, kind: str, occasion: dict | None = None) -> dict:
    """답글 하나 → {text, source(AGENT|FALLBACK|TEMPLATE), notes}. 언제나 글이 나온다."""
    if not config.agent_on("reply"):
        return {"text": template(view, review, occasion), "source": "TEMPLATE", "notes": []}
    task = {"kind": kind, "review_id": review["id"], "occasion": occasion}
    proposal = runner.run(SPEC, task, run_context(view))
    if proposal is None:
        return {"text": template(view, review, occasion), "source": "TEMPLATE", "notes": []}
    return {"text": proposal.content["text"], "source": proposal.source, "notes": proposal.notes}
