"""리뷰 분류 진입 함수.

리뷰마다 HyperCLOVA X 로 분류하고, 실패하면 키워드 규칙으로 대신한다.
불만 묶음과 빠른 응대 여부는 모델이 아니라 코드로 붙인다.
"""

import datetime as dt
from collections.abc import Callable, Iterable

from app.analysis.result_shapes import ReviewLabelRow
from app.analysis.review.complaint_groups import groups_of, is_quick, sort_types
from app.analysis.review.hcx_classifier import classify_with_hcx
from app.analysis.review.keyword_rules import classify_by_keywords
from app.planner.data_shapes import Review

# 리뷰 본문 → (감정, 불만 유형 목록). 실패하면 None.
Classifier = Callable[[str], tuple[str, list[str]] | None]


def label_text(review_id: str, text: str, now: dt.datetime, classifier: Classifier | None) -> ReviewLabelRow:
    """리뷰 한 건을 분류한다. classifier 가 없거나 실패하면 키워드 규칙을 쓰고 labeler 를 RULE 로 남긴다."""
    result = classifier(text) if classifier is not None else None
    labeler = "HCX"
    if result is None:
        result, labeler = classify_by_keywords(text), "RULE"
    sentiment, types = result
    types = sort_types(types)
    groups = groups_of(types)
    return ReviewLabelRow(
        review_id=review_id,
        sentiment=sentiment,
        complaint_types=types,
        complaint_groups=groups,
        is_quick=is_quick(groups),
        labeler=labeler,
        labeled_at=now,
    )


def label_reviews(
    reviews: Iterable[Review],
    now: dt.datetime,
    classifier: Classifier | None = classify_with_hcx,
) -> list[ReviewLabelRow]:
    """now 까지 쓰인 리뷰 중 아직 분류되지 않은 것(label 이 없는 것)만 분류한다.

    labeled_at 은 now 다. classifier=None 이면 모델을 부르지 않고 키워드 규칙만 쓴다.
    """
    return [
        label_text(review.review_id, review.text, now, classifier)
        for review in reviews
        if review.label is None and review.written_at <= now
    ]


def attach_labels(reviews: Iterable[Review], rows: Iterable[ReviewLabelRow]) -> list[Review]:
    """분류 결과를 계획 엔진 입력의 Review.label 에 붙인다. 결과가 없는 리뷰는 그대로 둔다."""
    labels = {row.review_id: row.to_label() for row in rows}
    return [
        review.model_copy(update={"label": labels[review.review_id]}) if review.review_id in labels else review
        for review in reviews
    ]
