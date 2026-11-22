"""2차 LLM 감사: 1차 코드 감사를 통과한 제출을 기준마다 좁은 질문 하나로 검사한다 (감사팀 계획 7장).

담당 SPEC.audit 이 여기 함수를 가리킨다. 모양은 Harness.spec.AuditFunc: (제출 인자, 근거, task, 맥락) → AuditVerdict.
- 질문은 quote_judge 로 묻는다. LLM 은 해당하는 부분을 글자 그대로 옮기기만 하고, 합격·불합격은 코드가 정한다.
- 기준은 정한 순서대로 묻고 처음 걸린 기준에서 멈춘다 (가정 i). 고친 뒤 다시 처음부터 본다 (같은 글·같은 질문은 캐시).
- 불합격(fail)이면 reason 이 담당에게 돌아갈 지적이다. 질문을 부르지 못하면 감사 못 함(unchecked).
- 업무 수첩 규칙 중 코드로 못 보는 것은 보지 않는다 (결정 13).
"""

import dataclasses

from app.analysis.review.hcx_classifier import mask_personal_info
from app.review_reply_writer.write_reply_with_clova import clean_answer
from Harness import guards
from Harness.agents import quote_judge, reply_critic
from Harness.grounding import Evidence
from Harness.spec import AuditVerdict, RunContext


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


def _verdict(counter: _Counter, status: str, reason: str | None = None, criterion: str | None = None,
             quotes: list[str] | None = None) -> AuditVerdict:
    return AuditVerdict(status, reason, {"criterion": criterion, "quotes": list(quotes or []), "calls": counter.calls})


def reply_job(review: dict) -> str:
    """답글 업무: 리뷰 분위기로 고른다 (같은 담당 voice_reply 가 두 업무를 맡는다)."""
    return "negative_reply" if review.get("sentiment") == "negative" else "positive_reply"


# ── 리뷰 답글 (negative_reply, positive_reply) ──


def reply(args: dict, evidence: Evidence, task: dict, ctx: RunContext) -> AuditVerdict:
    ctx, counter = _counted(ctx)
    review = ctx.snapshot.review(task["review_id"]) or {}
    text = clean_answer(str(args.get("text") or ""))
    verdict = reply_critic.inspect(
        text, ctx, review_text=mask_personal_info(review.get("text", "")), has_complaint=review.get("sentiment") == "negative",
    )
    if verdict is None:  # 마지막 질문을 못 불렀다: 지금처럼 정규식으로 대신 거르고, 걸리지 않으면 감사 못 함
        facts = [str(f).strip() for f in args.get("facts_used") or [] if str(f).strip()]
        caught = guards.first(guards.memory(text), None if any(f in text for f in facts) else guards.made_up_fact(text))
        return _verdict(counter, "fail", caught, "regex") if caught else _verdict(counter, "unchecked")
    if not verdict.ok:
        reason = "검토에서 걸렸어요: " + "; ".join(v.describe() for v in verdict.violations)
        return _verdict(counter, "fail", reason, verdict.violations[0].kind, [v.quote for v in verdict.violations])
    return _verdict(counter, "pass")


# ── 알바생 할 일 (review_fix_task, field_task) ──


def _outside(title: str, detail: str, ctx: RunContext, review_text: str | None = None) -> list[str] | None:
    return quote_judge.ask("staff_scope", f"{title}. {detail}", ctx, review_text=review_text)


def fix_card(args: dict, evidence: Evidence, task: dict, ctx: RunContext) -> AuditVerdict:
    ctx, counter = _counted(ctx)
    if args.get("actionable") is not True:  # 할 일이 아니다 (카드 없음)
        return _verdict(counter, "pass")
    review = ctx.snapshot.review(task["review_id"]) or {}
    title, detail = (args.get("title") or "").strip(), (args.get("detail") or "").strip()
    outside = _outside(title, detail, ctx, mask_personal_info(review.get("text", "")))
    if outside is None:
        return _verdict(counter, "unchecked")
    if outside:
        return _verdict(counter, "fail", f"알바생이 지금 있는 것으로 할 수 없는 일이 있어요: {', '.join(outside)}. "
                        "알바생이 할 수 있는 일만 써 주세요", "staff_scope", outside)
    return _verdict(counter, "pass")


def field_tasks(args: dict, evidence: Evidence, task: dict, ctx: RunContext) -> AuditVerdict:
    ctx, counter = _counted(ctx)
    for n, item in enumerate(args.get("items") or [], 1):
        title, detail = (item.get("title") or "").strip(), (item.get("detail") or "").strip()
        outside = _outside(title, detail, ctx)
        if outside is None:
            return _verdict(counter, "unchecked")
        if outside:
            return _verdict(counter, "fail", f"{n}번째 할 일에 알바생이 지금 있는 것으로 할 수 없는 일이 있어요: {', '.join(outside)}",
                            "staff_scope", outside)
    return _verdict(counter, "pass")
