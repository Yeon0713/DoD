"""리뷰 분류 진입 함수 (app/analysis/review/label_reviews.py).

모델은 가짜 함수로 바꿔 넣고, 마지막에는 계획 엔진 테스트 입력의 라벨을 지운 뒤 다시 붙여서 계획이 같은지 본다.
"""

import datetime as dt
import json
from pathlib import Path

import pytest

from app.analysis.review.label_reviews import attach_labels, label_reviews
from app.planner.data_shapes import PlanInputs, Review
from app.planner.make_plan import make_plan

PLANNER_INPUTS = Path(__file__).parents[1] / "planner" / "sample_inputs" / "demo_week_inputs.example.json"
RAW = json.loads(PLANNER_INPUTS.read_text(encoding="utf-8"))
END_OF_WEEK = dt.datetime.fromisoformat("2026-11-22T23:59:00+09:00")


def unlabeled_reviews() -> list[Review]:
    return [Review.model_validate({**review, "label": None}) for review in RAW["reviews"]]


def by_id(rows):
    return {row.review_id: row for row in rows}


def test_model_result_is_used_with_hcx_labeler():
    rows = label_reviews(unlabeled_reviews(), END_OF_WEEK, classifier=lambda text: ("NEGATIVE", ["SERVICE"]))
    row = rows[0]
    assert (row.labeler, row.complaint_types, row.complaint_groups, row.is_quick) == ("HCX", ["SERVICE"], ["SERVICE"], True)


def test_keyword_rules_used_when_model_fails():
    rows = by_id(label_reviews(unlabeled_reviews(), END_OF_WEEK, classifier=lambda text: None))
    assert all(row.labeler == "RULE" for row in rows.values())
    assert rows["rv_118"].complaint_types == ["DELIVERY_DELAY"] and rows["rv_118"].is_quick


def test_classifier_none_uses_keyword_rules_only():
    rows = label_reviews(unlabeled_reviews(), END_OF_WEEK, classifier=None)
    assert {row.labeler for row in rows} == {"RULE"}


def test_types_are_sorted_and_groups_follow():
    rows = label_reviews(unlabeled_reviews()[:1], END_OF_WEEK, classifier=lambda text: ("NEGATIVE", ["SERVICE", "TASTE", "SERVICE"]))
    assert rows[0].complaint_types == ["TASTE", "SERVICE"]
    assert rows[0].complaint_groups == ["FOOD", "SERVICE"]


def test_reviews_written_after_now_are_skipped():
    now = dt.datetime.fromisoformat("2026-11-17T12:00:00+09:00")
    ids = set(by_id(label_reviews(unlabeled_reviews(), now, classifier=None)))
    assert "rv_112" in ids  # 11/16 13:00
    assert "rv_118" not in ids  # 11/17 12:30


def test_already_labeled_reviews_are_skipped():
    reviews = [Review.model_validate(review) for review in RAW["reviews"]]  # 모두 label 이 있다
    assert label_reviews(reviews, END_OF_WEEK, classifier=None) == []


def test_labeled_at_is_now():
    now = dt.datetime.fromisoformat("2026-11-17T13:50:00+09:00")
    rows = label_reviews(unlabeled_reviews(), now, classifier=None)
    assert rows and all(row.labeled_at == now for row in rows)


def test_attach_labels_fills_only_labeled_reviews():
    reviews = unlabeled_reviews()
    rows = [row for row in label_reviews(reviews, END_OF_WEEK, classifier=None) if row.review_id == "rv_118"]
    attached = {review.review_id: review for review in attach_labels(reviews, rows)}
    assert attached["rv_118"].label is not None and attached["rv_118"].label.is_quick
    assert attached["rv_087"].label is None


@pytest.mark.parametrize("now", [
    "2026-11-16T10:00:00+09:00",
    "2026-11-17T14:00:00+09:00",
    "2026-11-20T21:30:00+09:00",
    "2026-11-22T23:59:00+09:00",
])
def test_keyword_labels_give_same_plan_as_planner_inputs(now):
    """라벨을 지우고 키워드 규칙으로 다시 붙여도 데모 주간 계획이 같다."""
    now = dt.datetime.fromisoformat(now)
    reviews = unlabeled_reviews()
    relabeled = attach_labels(reviews, label_reviews(reviews, END_OF_WEEK, classifier=None))
    inputs = PlanInputs.model_validate({**RAW, "reviews": [review.model_dump(mode="json") for review in relabeled]})
    expected = make_plan(PlanInputs.model_validate(RAW), now)
    assert make_plan(inputs, now).model_dump() == expected.model_dump()
