"""F2 리뷰 나누고 줄이기 (규칙, LLM 없음).

기존 키워드 규칙(app/analysis/review/keyword_rules.classify_by_keywords)을 쓰고, 이름을 문서 모양으로 바꾼다.
  sentiment: POSITIVE → positive, NEGATIVE·MIXED → negative. 별점 2 이하는 글과 상관없이 negative
  topic:     DELIVERY_DELAY → delivery, TASTE → taste, PORTION → portion, SERVICE → service, HYGIENE → hygiene,
             PHOTO_MISMATCH·없음 → other. 좋은 리뷰는 좋아한 점(strengths)으로 정한다
  summary:   주제별 한 줄 (화면 폭 17 안)
"""

from app.analysis.review.keyword_rules import classify_by_keywords
from voice import width
from voice.jobs import strengths

TOPICS = {"DELIVERY_DELAY": "delivery", "TASTE": "taste", "PORTION": "portion", "SERVICE": "service", "HYGIENE": "hygiene"}
NEGATIVE_SUMMARIES = {
    "delivery": "배달이 늦었대요",
    "taste": "맛이 아쉬웠대요",
    "portion": "양이 적었대요",
    "service": "응대가 아쉬웠대요",
    "hygiene": "위생이 걱정됐대요",
    "other": "아쉬운 점이 있었대요",
}
POSITIVE_SUMMARIES = {
    "taste": "맛있게 드셨대요",
    "service": "응대가 친절했대요",
    "portion": "양이 넉넉했대요",
    "delivery": "배달이 빨랐대요",
    "other": "좋게 봐 주셨어요",
}
STRENGTH_TOPICS = {"soup": "taste", "kind": "service", "portion": "portion", "fast": "delivery"}


def classify(text: str, rating: int) -> tuple[str, str]:
    sentiment, types = classify_by_keywords(text)
    negative = sentiment != "POSITIVE" or rating <= 2
    if negative:
        topic = next((TOPICS[t] for t in types if t in TOPICS), "other")
        return "negative", topic
    found = strengths.keys_in(text)
    return "positive", STRENGTH_TOPICS.get(found[0], "other") if found else "other"


def summarize(text: str, sentiment: str, topic: str) -> str:
    if sentiment == "negative":
        if topic == "delivery" and "식" in text:
            return width.fit("review.summary", "배달이 늦어 음식이 식었대요", NEGATIVE_SUMMARIES[topic])
        return NEGATIVE_SUMMARIES[topic]
    if topic == "taste" and "국물" in text:
        return "국물 맛이 좋았대요"
    return POSITIVE_SUMMARIES[topic]


def label(review: dict) -> dict:
    """리뷰 한 건에 sentiment, topic, summary 를 붙여 돌려준다 (저장은 부르는 쪽이)."""
    sentiment, topic = classify(review["text"], int(review.get("rating") or 0))
    return {**review, "sentiment": sentiment, "topic": topic, "summary": summarize(review["text"], sentiment, topic)}
