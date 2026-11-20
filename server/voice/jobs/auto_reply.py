"""F3 아쉬운 리뷰에 바로 답하기 (부정 리뷰 답글 직급이 대리·과장일 때만, voice/hr.py), 예약한 답글 올리기.

'올린다' = reply_status 를 posted 로 바꾸고 reply_posted_at 을 적는 것 (v0.2.0 은 실제 플랫폼에 올리지 않는다, 문서 9장).
reply_summary(화면 폭 32 안)는 주제별 템플릿이다. 답글 본문을 줄이는 LLM 호출은 하지 않는다.
밤사이 아쉬운 리뷰 (2026-11-20, 안 B): 교정 카드(부정 리뷰 사원)를 먼저 정해 답글이 같은 조치를 약속하게 하고,
할 일은 바로 넣지 않고 다음 아침 브리핑에서 묻도록 제안으로 남긴다 (jobs/staff_tasks.py).
"""

import datetime as dt

from voice import clock, config, hr, proposals, repo
from voice.agents import fix_card, voice_reply
from voice.clock import parse
from voice.context import load

REPLY_SUMMARIES = {
    "delivery": "사과하고, 다음엔 더 빨리 보낸다고 답했어요",
    "taste": "사과하고, 간을 다시 확인한다고 답했어요",
    "portion": "사과하고, 양을 다시 살핀다고 답했어요",
    "service": "사과하고, 더 세심히 챙긴다고 답했어요",
    "hygiene": "사과하고, 위생을 다시 점검한다고 답했어요",
    "other": "사과하고, 꼭 살펴보겠다고 답했어요",
}


def eligible(review: dict, now: dt.datetime) -> bool:
    if review.get("sentiment") != "negative" or review.get("reply_status", "none") != "none" or review.get("reply_deleted_at"):
        return False
    written = parse(review["written_at"])
    return written <= now <= written + config.AUTO_REPLY_WINDOW


def reply_now(store_id: str, review_id: str) -> dict | None:
    """리뷰 한 건에 바로 답한다. 대리·과장이 아니거나, 이미 답했거나, 30분이 지났으면 아무것도 하지 않는다.
    인턴·사원이면 아침 브리핑 준비(draft_negative)가 써 두고 "올릴까요?"로 묻는다."""
    if hr.asks(store_id, "negative_reply") is not None:
        return None
    view = load(store_id)
    review = view.review(review_id) if view else None
    now = clock.now()
    if review is None or not eligible(review, now):
        return None
    found = fix_card.card_for(view, review)
    fix = {"cause": found["summary"], "action": found["card"]["detail"], "reply": found["reply"]} if found["card"] else None
    written = voice_reply.write(view, review, "AUTO", fix=fix)
    propose_overnight(store_id, review, found, now)
    posted = clock.now()  # 에이전트가 도는 동안 흐른 시간까지 (실제 시계일 때)
    review.update({
        "reply_status": "posted", "reply_by": "donna", "reply_text": written["text"], "reply_source": written["source"],
        "reply_notes": written["notes"], "reply_summary": REPLY_SUMMARIES[review.get("topic") or "other"],
        "reply_posted_at": clock.iso(posted), "replied_in_minutes": max(1, round((posted - parse(review["written_at"])).total_seconds() / 60)),
    })
    saved = repo.save_review(review)
    hr.record(store_id, "negative_reply", review_id, "done")
    return saved


def propose_overnight(store_id: str, review: dict, found: dict, now: dt.datetime) -> dict | None:
    """밤사이 아쉬운 리뷰의 교정 카드를 다음 아침 브리핑에서 묻도록 제안으로 남긴다. 같은 리뷰로는 한 번만."""
    from voice.jobs import staff_tasks

    if not found["card"] or proposals.for_review(store_id, review["id"]):
        return None
    return staff_tasks.propose_fix(store_id, review, found["card"], ask_on=staff_tasks.briefing_day(repo.store(store_id), now))


def reply_pending(store_id: str) -> list[str]:
    """지금 답할 수 있는 아쉬운 리뷰 모두에 바로 답한다 (dev/run auto_reply)."""
    done = []
    for review in repo.reviews(store_id):
        if reply_now(store_id, review["id"]):
            done.append(review["id"])
    return done


def post_scheduled(store_id: str) -> list[str]:
    """올릴 시각이 지난 예약 답글을 올린다."""
    now = clock.now()
    posted = []
    for review in repo.reviews(store_id):
        if review.get("reply_status") == "scheduled" and parse(review["reply_post_at"]) <= now:
            review.update({"reply_status": "posted", "reply_posted_at": review["reply_post_at"]})
            repo.save_review(review)
            if review.get("reply_trigger") == "auto":  # 묻지 않고 예약한 칭찬 답글 (대리·과장, 인사과 4-b)
                hr.record(store_id, "positive_reply", review["id"], "done")
            posted.append(review["id"])
    return posted
