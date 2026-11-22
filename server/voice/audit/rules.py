"""1차 코드 감사: 담당마다 제출을 코드로 검사한다 (감사팀 계획 6장, 16장 2단계).

담당 SPEC.check 가 여기 함수를 가리킨다. 써도 되면 None, 안 되면 담당에게 돌려줄 거절 이유.
LLM 으로 뜻을 보는 검사(reply_critic, staff_scope)는 2차 감사(inspector.py)에 있다.
모양은 Harness.spec.CheckFunc: (제출 인자, 근거, task, 맥락, notes).
담당 모듈의 도구·상수는 함수 안에서 읽는다 (담당 모듈이 이 모듈을 import 하므로 맨 위에서 읽으면 서로 물린다).
"""

import datetime as dt

from app.analysis.review.hcx_classifier import mask_personal_info
from app.review_reply_writer.write_reply_with_clova import MAX_LENGTH, MIN_LENGTH, clean_answer
from Harness import guards
from Harness.grounding import Evidence, ungrounded_numbers
from Harness.spec import RunContext
from voice import notebook, width
from voice.similar import dice

UNCHECKED = "검토 안 됨"  # 2차 감사를 못 했을 때 답글 notes 에 남기는 말


def _texts(args: dict, key: str) -> list[str]:
    value = args.get(key) or []
    return [str(v).strip() for v in value if str(v).strip()] if isinstance(value, list) else []


# ── 리뷰 답글 (voice_reply) ──


def reply_code(args: dict, task: dict, ctx: RunContext) -> str | None:
    """답글의 코드 검사: 길이, 빈칸, 가격·할인, 메뉴·사실 메모 대조, 수첩 금지어, quoted_review_words 가 리뷰에 글자 그대로 있는지.
    단일 에이전트 비교(Harness/agents/single_agent.py)도 이것을 쓴다."""
    from voice.agents import voice_reply

    view = ctx.snapshot
    review = view.review(task["review_id"]) or {}
    text = clean_answer(str(args.get("text") or ""))
    quoted, menus, facts = _texts(args, "quoted_review_words"), _texts(args, "menus_mentioned"), _texts(args, "facts_used")
    reason = guards.first(
        guards.length(text, MIN_LENGTH, MAX_LENGTH, "답글"),
        guards.placeholder(text),
        guards.price_or_discount(text),
        guards.not_in(menus, [m["name"] for m in view.menus], "메뉴 이름"),
        guards.not_in(facts, ctx.store_facts, "가게 사실(get_store_facts 에 있는 문장만 쓸 수 있어요)"),
        notebook.checks(ctx.store_id, voice_reply.notebook_agent(task, ctx), text),  # 사장님 수첩의 금지 낱말·이모티콘
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
    return None


def reply(args: dict, evidence: Evidence, task: dict, ctx: RunContext, notes: list[str]) -> str | None:
    return reply_code(args, task, ctx)


# ── 리뷰 교정 할 일 (fix_card) ──


def fix_card(args: dict, evidence: Evidence, task: dict, ctx: RunContext, notes: list[str]) -> str | None:
    review = ctx.snapshot.review(task["review_id"]) or {}
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
    return guards.first(guards.price_or_discount(f"{title} {detail}"), guards.promise(f"{title} {detail}"))


# ── 현장 변수 할 일 (field_tasks) ──


def field_tasks(args: dict, evidence: Evidence, task: dict, ctx: RunContext, notes: list[str]) -> str | None:
    from voice.agents import field_tasks as agent

    items = args.get("items")
    if not isinstance(items, list):
        return "items 는 목록이어야 해요"
    if len(items) > agent.MAX_ITEMS:
        return f"할 일은 {agent.MAX_ITEMS}개까지만 내 주세요"
    for n, item in enumerate(items, 1):
        title, detail = (item.get("title") or "").strip(), (item.get("detail") or "").strip()
        quote = (item.get("quote") or "").strip()
        if not title or not detail or item.get("phase") not in agent.PHASE_OF:
            return f"{n}번째 할 일의 title, detail 을 채우고 phase 는 {', '.join(agent.PHASE_LABELS)} 중 하나로 써 주세요"
        source = agent.source_text(ctx, item)
        if not source:
            return f"{n}번째 할 일의 source_id '{item.get('source_id')}' 는 오늘 날씨·예약에 없어요"
        if not quote or quote not in source:
            return f"{n}번째 할 일의 quote 는 근거 도구 결과에서 글자 그대로 옮겨 주세요"
        if not width.fits(title, "staff.title"):
            return f"{n}번째 할 일의 " + width.too_long("title", title, "staff.title")
        if not width.fits(detail, "staff.detail"):
            return f"{n}번째 할 일의 " + width.too_long("detail", detail, "staff.detail")
        reason = guards.first(guards.price_or_discount(f"{title} {detail}"), guards.promise(f"{title} {detail}"))
        if reason:
            return reason
        loose = ungrounded_numbers(f"{title} {detail}", evidence)
        if loose:
            return f"{n}번째 할 일에 도구 결과에 없는 숫자가 있어요: {', '.join(dict.fromkeys(loose))}"
        allergies = agent.ALLERGY_RE.findall(f"{title} {detail}")
        made_up = [a for a in allergies if a not in source]  # 손님 정보는 그 할 일의 근거(그 예약 메모)에만 있어야 한다
        if made_up:
            return (f"{n}번째 할 일의 알레르기({', '.join(made_up)})는 그 할 일의 근거에 없어요. "
                    "알레르기는 그 예약 메모를 근거로 한 할 일에만, 메모에 적힌 그대로 써 주세요")
    return None


# ── 매뉴얼화 제안 (manual_line) ──

MIN_OVERLAP = 0.2  # 다듬은 글이 묶음 안 할 일 하나와는 이만큼 겹쳐야 한다 (없는 행동을 지어내지 않게)


def manual_line(args: dict, evidence: Evidence, task: dict, ctx: RunContext, notes: list[str]) -> str | None:
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


# ── 인스타 소재 (topic_finder) ──


def topic_finder(args: dict, evidence: Evidence, task: dict, ctx: RunContext, notes: list[str]) -> str | None:
    from voice.agents.topic_finder import TOP

    ids = [str(i) for i in args.get("menu_ids") or []]
    with_photo = {m["id"] for m in ctx.snapshot.menus if m.get("photo_url")}
    if not 1 <= len(ids) <= 3:
        return "menu_ids 는 1~3개로 골라 주세요"
    if len(set(ids)) != len(ids) or any(i not in with_photo for i in ids):
        return f"menu_ids 는 사진이 있는 메뉴 id 중에서만 골라 주세요: {', '.join(sorted(with_photo))}"
    angle = (args.get("angle") or "").strip()
    if not angle or not width.fits(angle, "tip"):
        return f"angle 은 한 줄로 짧게 써 주세요 (폭 {width.LIMITS['tip']} 이하)"
    reason = guards.first(guards.price_or_discount(angle), guards.promise(angle))
    if reason:
        return reason
    loose = ungrounded_numbers(angle, evidence)
    if loose:
        return f"도구 결과에 없는 숫자를 썼어요: {', '.join(dict.fromkeys(loose))}"
    claims = guards.sales_claim_words(angle)
    if claims and TOP not in evidence.sources():
        return f"'{', '.join(claims)}' 같은 판매 이야기는 {TOP} 로 매출을 본 뒤에만 쓸 수 있어요"
    return None


# ── 인스타 글 (caption_writer) ──


def caption_writer(args: dict, evidence: Evidence, task: dict, ctx: RunContext, notes: list[str]) -> str | None:
    from voice.agents.caption_writer import MAX_BODY, MAX_TAGS, MIN_BODY, QUOTED_RE, TAG_RE

    body = (args.get("body") or "").strip()
    tags = [str(t).strip() for t in args.get("hashtags") or []]
    if not MIN_BODY <= len(body) <= MAX_BODY:
        return f"본문은 {MIN_BODY}~{MAX_BODY}자로 써 주세요 (지금 {len(body)}자)"
    if len(tags) > MAX_TAGS or any(not TAG_RE.match(t) for t in tags):
        return f"해시태그는 #으로 시작하는 한 낱말로 {MAX_TAGS}개까지만 써 주세요"
    reason = guards.first(guards.price_or_discount(body), guards.promise(body), notebook.checks(ctx.store_id, "marketing", body))
    if reason:
        return reason
    loose = ungrounded_numbers(body, evidence)
    if loose:
        return f"입력에 없는 숫자를 썼어요: {', '.join(dict.fromkeys(loose))}"
    quoted = [q for q in QUOTED_RE.findall(body) if q.strip()]
    if quoted and any(q.strip() != (task.get("quote") or "") for q in quoted):
        return "따옴표 안의 손님 한마디는 주어진 글자 그대로만 쓸 수 있어요"
    return None


# ── 휴무 읽기 (holiday_reader) ──


def holiday_reader(args: dict, evidence: Evidence, task: dict, ctx: RunContext, notes: list[str]) -> str | None:
    from voice.holidays import AHEAD

    found = args.get("items")
    if not isinstance(found, list):
        return "items 는 목록이어야 해요"
    today = ctx.now.date()
    joined = "\n".join(task["texts"])
    for item in found:
        try:
            day = dt.date.fromisoformat(str(item.get("date")))
        except ValueError:
            return f"date '{item.get('date')}' 는 YYYY-MM-DD 로 써 주세요"
        if not today <= day <= today + AHEAD:
            return f"{day} 는 오늘부터 60일 안의 날이 아니에요. 지난 휴무나 먼 날은 빼 주세요"
        if not (item.get("quote") or "").strip() or item["quote"].strip() not in joined:
            return "quote 는 네이버 글에서 글자 그대로 옮겨 주세요"
    return None


# ── 고칠 점 (improve_tip) ──


def improve_tip(args: dict, evidence: Evidence, task: dict, ctx: RunContext, notes: list[str]) -> str | None:
    tip = str(args.get("tip") or "").strip()
    if width.width(tip) < 8:
        return "고칠 점이 너무 짧아요"
    if not width.fits(tip, "tip"):
        return f"고칠 점이 너무 길어요 (화면 폭 {width.width(tip)}, 34 이하로. 한글은 1, 숫자·공백은 0.5)"
    if not tip.rstrip(".!").endswith("요"):
        return "'~해 보세요'처럼 '요'로 끝나게 써 주세요"
    reason = guards.first(guards.promise(tip), guards.price_or_discount(tip))
    if reason:
        return reason
    if not args.get("evidence"):
        return "evidence 에 근거를 1개 이상 적어 주세요"
    loose = ungrounded_numbers(tip, evidence)
    if loose:
        return f"도구 결과에 없는 숫자를 썼어요: {', '.join(dict.fromkeys(loose))}. 그 숫자를 빼 주세요"
    return None
