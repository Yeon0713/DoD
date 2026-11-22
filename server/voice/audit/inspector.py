"""2차 LLM 감사: 1차 코드 감사를 통과한 제출을 기준마다 좁은 질문 하나로 검사한다 (감사팀 계획 7장).

담당 SPEC.audit 이 업무별 감사 함수(reply, fix_card, field_tasks, manual_line, topic_finder, caption_writer, holiday_reader)를 가리킨다.
모양은 Harness.spec.AuditFunc: (제출 인자, 근거, task, 맥락) → AuditVerdict.
- 질문은 quote_judge 로 묻는다. LLM 은 해당하는 부분을 글자 그대로 옮기기만 하고, 합격·불합격은 코드가 정한다.
- 기준은 정한 순서대로 묻고 처음 걸린 기준에서 멈춘다 (가정 i). 고친 뒤 다시 처음부터 본다 (같은 글·같은 질문은 캐시).
- 불합격(fail)이면 reason 이 담당에게 돌아갈 지적이다. 어느 기준을 부르지 못하면, 다른 기준에 걸리지 않는 한 감사 못 함(unchecked).
- 업무 수첩 규칙 중 코드로 못 보는 것은 보지 않는다 (결정 13).
- improve_tip(고칠 점)은 기준만 두고 담당에 잇지 않는다 (가정 h).
- 판정 세트 목표(놓침 5%·오탐 10% 이하, 결정 14)를 넘은 기준만 담당에 잇는다 (18장 3번: 실행 중 스위치 대신 개발 규칙).
  2026-11-22: 처음 측정에서 3개만 넘었고, 프롬프트를 다듬어 다시 재 10개 모두 넘었다 (audit-team-plan.md 16장 끝 "5단계 측정").
  기준을 고치면 python -m Harness.evals audit 으로 다시 재고, 못 넘으면 그 기준을 업무별 감사에서 뺀다.

기준 하나는 Finding(불합격·감사 못 함) 또는 None(합격)을 돌려준다. judge_case 는 판정 세트 평가(Harness/evals/audit_eval.py)가 부른다.
"""

import dataclasses
import datetime as dt
import re
from typing import NamedTuple

from app.analysis.review.hcx_classifier import mask_personal_info
from app.review_reply_writer.write_reply_with_clova import clean_answer
from Harness import guards
from Harness.agents import quote_judge, reply_critic
from Harness.grounding import Evidence
from Harness.spec import AuditVerdict, RunContext
from voice.audit import questions as q


class Finding(NamedTuple):
    status: str  # "fail" | "unchecked"
    reason: str | None = None
    criterion: str | None = None
    quotes: tuple[str, ...] = ()


UNCHECKED = Finding("unchecked")


class _Counter:
    """감사가 실제로 CLOVA 를 부른 수 (캐시된 판정은 세지 않는다)."""

    def __init__(self, post):
        self.post, self.calls = post, 0

    def __call__(self, *args, **kwargs):
        self.calls += 1
        return self.post(*args, **kwargs)


def _counted(ctx: RunContext) -> tuple[RunContext, _Counter]:
    counter = _Counter(ctx.post)
    return dataclasses.replace(ctx, post=counter), counter


def _decide(counter: _Counter, findings) -> AuditVerdict:
    """기준들을 차례로 본다 (기준이 여럿이면 하나씩 부르는 생성기로 받아 처음 불합격에서 멈춘다). 감사 못 한 기준이 있으면 unchecked."""
    unchecked = False
    for found in findings:
        if found is None:
            continue
        if found.status == "fail":
            return AuditVerdict("fail", found.reason, {"criterion": found.criterion, "quotes": list(found.quotes), "calls": counter.calls})
        unchecked = True
    return AuditVerdict("unchecked" if unchecked else "pass", None, {"criterion": None, "quotes": [], "calls": counter.calls})


def _require(question, text: str, ctx: RunContext, context: str, criterion: str, reason: str) -> Finding | None:
    """해당하는 부분이 있어야 합격."""
    found = quote_judge.ask(question, text, ctx, review_text=context)
    if found is None:
        return UNCHECKED
    return Finding("fail", reason, criterion) if not found else None


def _forbid(question, text: str, ctx: RunContext, context: str | None, criterion: str, reason) -> Finding | None:
    """해당하는 부분이 없어야 합격. reason(quotes) → 지적."""
    found = quote_judge.ask(question, text, ctx, review_text=context)
    if found is None:
        return UNCHECKED
    return Finding("fail", reason(found), criterion, tuple(found)) if found else None


def _joined(quotes: list[str]) -> str:
    return ", ".join(f"'{part}'" for part in quotes)


# ── 기준 (7-2) ──


def card_promise(text: str, action: str, ctx: RunContext) -> Finding | None:
    return _require(q.CARD_PROMISE, text, ctx, action, "card_promise",
                    f"교정 카드 조치('{action}')를 하겠다는 말이 없어요. 사과와 함께 이 조치를 한 문장으로 넣어 주세요")


def occasion_claim(text: str, occasion: str, ctx: RunContext) -> Finding | None:
    return _forbid(q.OCCASION_CLAIM, text, ctx, occasion, "occasion_claim",
                   lambda found: f"올리는 날 정보에 없는 이야기예요: {_joined(found)}. 빼거나 올리는 날 정보에 맞게 고쳐 주세요")


def staff_scope(title: str, detail: str, ctx: RunContext, review_text: str | None = None, n: int | None = None) -> Finding | None:
    def reason(found):
        if n is None:
            return f"알바생이 지금 있는 것으로 할 수 없는 일이 있어요: {', '.join(found)}. 알바생이 할 수 있는 일만 써 주세요"
        return f"{n}번째 할 일에 알바생이 지금 있는 것으로 할 수 없는 일이 있어요: {', '.join(found)}"

    return _forbid("staff_scope", f"{title}. {detail}", ctx, review_text, "staff_scope", reason)


def fix_relevance(title: str, detail: str, complaint: str, ctx: RunContext) -> Finding | None:
    return _require(q.FIX_RELEVANCE, f"{title}. {detail}", ctx, complaint, "fix_relevance",
                    f"이 할 일은 리뷰 불만('{complaint}')을 줄이지 않아요. 그 불만을 직접 줄이는 행동으로 써 주세요")


NOUNS_ENDING_GO = {"냉장고", "창고", "광고", "재고", "최고", "사고", "금고"}  # "~고"로 끝나지만 이어 주는 말이 아닌 낱말


def split_actions(text: str) -> list[str]:
    """할 일 한 문장을 행동으로 나눈다: 쉼표·"그리고", 그리고 "~고"로 끝나는 낱말 뒤 ("랩을 씌우고 테이프를 붙여 주세요" → 둘).
    "~한 뒤", "~전에", "~하면" 같은 때·조건은 나누지 않는다."""
    actions = []
    for part in re.split(r",\s*|\s+그리고\s+", text.strip().rstrip(".")):
        words: list[str] = []
        for word in part.split():
            words.append(word)
            if word.endswith("고") and word not in NOUNS_ENDING_GO:
                actions.append(" ".join(words))
                words = []
        if words:
            actions.append(" ".join(words))
    return [a for a in actions if a] or [text.strip()]


def _each_action(text: str, ctx: RunContext, question, context: str, criterion: str, reason) -> Finding | None:
    """코드가 행동을 나누고(split_actions), 행동마다 question 이 참이어야 합격. 처음 걸린 행동에서 멈춘다.
    text 는 할 일 내용(detail)만 준다. 제목은 내용을 줄인 것이라 행동이 겹친다."""
    unchecked = False
    for action in split_actions(text):
        found = quote_judge.ask(question, action, ctx, review_text=context)
        if found is None:
            unchecked = True
        elif not found:
            return Finding("fail", reason(action), criterion, (action,))
    return UNCHECKED if unchecked else None


def field_link(title: str, detail: str, source: str, quote: str, ctx: RunContext, n: int = 1) -> Finding | None:
    return _each_action(detail, ctx, q.FIELD_NEED, source, "field_link",
                        lambda action: f"{n}번째 할 일의 '{action}'는 근거('{quote}')와 상관없어요")


def today_need(title: str, detail: str, source: str, ctx: RunContext, n: int = 1) -> Finding | None:
    return _require(q.TODAY_NEED, f"{title}. {detail}", ctx, source, "today_need",
                    f"{n}번째 할 일은 오늘 안 해도 손님이 바로 겪지 않아요. today_impact 를 false 로 내 주세요")


def manual_added(title: str, detail: str, items: list[str], ctx: RunContext) -> Finding | None:
    return _each_action(detail, ctx, q.MANUAL_SAME, " / ".join(items), "manual_added",
                        lambda action: f"'{action}'는 반복해서 넣은 할 일에 없는 행동이에요. 빼 주세요")


def angle_menu(angle: str, menus: list[str], ctx: RunContext) -> Finding | None:
    return _forbid(q.ANGLE_MENU, angle, ctx, ", ".join(menus), "angle_menu",
                   lambda found: f"이야기 {_joined(found)}는 고른 메뉴와 상관없어요")


def caption_off(body: str, menus: list[str], angle: str, ctx: RunContext) -> Finding | None:
    return _forbid(q.CAPTION_OFF, body, ctx, f"메뉴 {', '.join(menus)} / 이야기 {angle}", "caption_off",
                   lambda found: f"{_joined(found)}는 올릴 메뉴·이야기와 상관없어요")


def store_claim(body: str, ctx: RunContext) -> Finding | None:
    """인스타 글의 가게 사실 주장이 가게가 등록한 사실(ctx.store_facts)과 맞는지 (질문은 인스타용 caption_claim, 판정은 reply_critic 과 같다)."""
    claims = quote_judge.ask(q.CAPTION_CLAIM, body, ctx)
    if claims is None:
        return UNCHECKED
    unbacked = [c for c in claims if not reply_critic.only_promises(c) and not reply_critic.backed_by_facts(c, ctx.store_facts)]
    return Finding("fail", f"가게가 등록한 사실에 없는 이야기예요: {_joined(unbacked)}", "store_claim", tuple(unbacked)) if unbacked else None


def _day_name(day: dt.date) -> str:
    return f"{day.month}월 {day.day}일"


def holiday_says(quote: str, day: dt.date, ctx: RunContext) -> Finding | None:
    return _require(q.HOLIDAY_SAYS, quote, ctx, f"{_day_name(day)} ({day.isoformat()})", "holiday_says",
                    f"'{quote}'는 {_day_name(day)}에 쉰다는 말이 아니에요. 그 날짜를 빼 주세요")


def tip_grounded(tip: str, reviews: list[str], ctx: RunContext) -> Finding | None:
    return _forbid(q.TIP_GROUNDED, tip, ctx, " / ".join(reviews), "tip_grounded",
                   lambda found: f"{_joined(found)}는 근거 리뷰들에 나오지 않는 문제예요. 근거 리뷰에 나온 문제로 써 주세요")


# ── 업무별 감사 ──


def reply_job(review: dict) -> str:
    """답글 업무: 리뷰 분위기로 고른다 (같은 담당 voice_reply 가 두 업무를 맡는다)."""
    return "negative_reply" if review.get("sentiment") == "negative" else "positive_reply"


def _critic(text: str, review: dict, args: dict, ctx: RunContext) -> Finding | None:
    """기존 기준 6개 (reply_critic). 마지막 질문을 못 부르면 지금처럼 정규식으로 대신 거르고, 걸리지 않으면 감사 못 함."""
    verdict = reply_critic.inspect(
        text, ctx, review_text=mask_personal_info(review.get("text", "")), has_complaint=review.get("sentiment") == "negative",
    )
    if verdict is None:
        facts = [str(f).strip() for f in args.get("facts_used") or [] if str(f).strip()]
        caught = guards.first(guards.memory(text), None if any(f in text for f in facts) else guards.made_up_fact(text))
        return Finding("fail", caught, "regex") if caught else UNCHECKED
    if not verdict.ok:
        reason = "검토에서 걸렸어요: " + "; ".join(v.describe() for v in verdict.violations)
        return Finding("fail", reason, verdict.violations[0].kind, tuple(v.quote for v in verdict.violations))
    return None


def occasion_text(task: dict, ctx: RunContext) -> str:
    """올리는 날 정보 (답글 담당의 get_reply_occasion 도구 결과와 같은 내용)."""
    from voice.agents.voice_reply import reply_occasion

    found = reply_occasion(ctx, task, {})
    return f"{found['label']} ({found['why']}), {found['post_day']}: " + ", ".join(found["that_day"])


def reply(args: dict, evidence: Evidence, task: dict, ctx: RunContext) -> AuditVerdict:
    ctx, counter = _counted(ctx)
    review = ctx.snapshot.review(task["review_id"]) or {}
    text = clean_answer(str(args.get("text") or ""))
    job = reply_job(review)

    def findings():
        yield _critic(text, review, args, ctx)
        if job == "negative_reply" and task.get("fix") and not task.get("revise"):  # 고쳐 쓰기는 사장님 지시가 우선
            yield card_promise(text, task["fix"]["action"], ctx)
        if job == "positive_reply" and task.get("occasion"):
            yield occasion_claim(text, occasion_text(task, ctx), ctx)

    return _decide(counter, findings())


def fix_card(args: dict, evidence: Evidence, task: dict, ctx: RunContext) -> AuditVerdict:
    ctx, counter = _counted(ctx)
    if args.get("actionable") is not True:  # 할 일이 아니다 (카드 없음)
        return _decide(counter, [])
    review = ctx.snapshot.review(task["review_id"]) or {}
    title, detail = (args.get("title") or "").strip(), (args.get("detail") or "").strip()


    def findings():
        yield staff_scope(title, detail, ctx, mask_personal_info(review.get("text", "")))
        yield fix_relevance(title, detail, (args.get("quote") or "").strip(), ctx)

    return _decide(counter, findings())


def field_tasks(args: dict, evidence: Evidence, task: dict, ctx: RunContext) -> AuditVerdict:
    from voice.agents.field_tasks import source_text

    ctx, counter = _counted(ctx)

    def findings():
        for n, item in enumerate(args.get("items") or [], 1):
            title, detail = (item.get("title") or "").strip(), (item.get("detail") or "").strip()
            source = source_text(ctx, item)
            yield staff_scope(title, detail, ctx, n=n)
            yield field_link(title, detail, source, (item.get("quote") or "").strip(), ctx, n)
            if item.get("today_impact") is True:
                yield today_need(title, detail, source, ctx, n)

    return _decide(counter, findings())


def manual_line(args: dict, evidence: Evidence, task: dict, ctx: RunContext) -> AuditVerdict:
    ctx, counter = _counted(ctx)
    title, detail = (args.get("title") or "").strip(), (args.get("detail") or "").strip()
    return _decide(counter, [manual_added(title, detail, task["items"], ctx)])


def topic_finder(args: dict, evidence: Evidence, task: dict, ctx: RunContext) -> AuditVerdict:
    ctx, counter = _counted(ctx)
    names = {m["id"]: m["name"] for m in ctx.snapshot.menus}
    menus = [names.get(str(i), str(i)) for i in args.get("menu_ids") or []]
    return _decide(counter, [angle_menu((args.get("angle") or "").strip(), menus, ctx)])


def caption_writer(args: dict, evidence: Evidence, task: dict, ctx: RunContext) -> AuditVerdict:
    ctx, counter = _counted(ctx)
    body = (args.get("body") or "").strip()

    def findings():
        yield caption_off(body, task["menus"], task["angle"], ctx)
        yield store_claim(body, ctx)

    return _decide(counter, findings())


def holiday_reader(args: dict, evidence: Evidence, task: dict, ctx: RunContext) -> AuditVerdict:
    ctx, counter = _counted(ctx)

    def findings():
        for item in args.get("items") or []:
            yield holiday_says((item.get("quote") or "").strip(), dt.date.fromisoformat(str(item["date"])), ctx)

    return _decide(counter, findings())


# ── 판정 세트 평가 ──


def judge_case(criterion: str, given: dict, output: dict, ctx: RunContext) -> bool | None:
    """판정 세트 사례 하나 (Harness/evals/data/audit_cases.json): 합격 True, 불합격 False, 감사 못 함 None."""
    title, detail = output.get("title", ""), output.get("detail", "")
    found = {
        "card_promise": lambda: card_promise(output["text"], given["action"], ctx),
        "occasion_claim": lambda: occasion_claim(output["text"], ", ".join(given["that_day"]), ctx),
        "fix_relevance": lambda: fix_relevance(title, detail, given["quote"], ctx),
        "field_link": lambda: field_link(title, detail, given["source"], given["source"], ctx),
        "today_need": lambda: today_need(title, detail, given["source"], ctx),
        "manual_added": lambda: manual_added(title, detail, given["items"], ctx),
        "angle_menu": lambda: angle_menu(output["angle"], given["menus"], ctx),
        "caption_off": lambda: caption_off(output["body"], given["menus"], given["angle"], ctx),
        "store_claim": lambda: store_claim(output["body"], ctx),
        "holiday_says": lambda: holiday_says(output["quote"], dt.date.fromisoformat(given["date"]), ctx),
    }[criterion]()
    if found is None:
        return True
    return None if found.status == "unchecked" else False
