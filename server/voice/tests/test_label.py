"""F2 리뷰 나누기 (voice/jobs/label.py). 별점이 없는 리뷰(네이버 플레이스에 흔하다)는 별점으로 판단하지 않는다."""

import pytest

from voice.jobs import label


@pytest.mark.parametrize("rating", [None, 5, 4.5])
def test_praise_without_low_rating_is_positive(rating):
    assert label.label({"text": "음식이 정말 맛있네요. 직원분들도 친절해요", "rating": rating})["sentiment"] == "positive"


@pytest.mark.parametrize("rating", [1, 2, 2.0])
def test_low_rating_is_negative_even_with_kind_words(rating):
    assert label.label({"text": "맛있어요", "rating": rating})["sentiment"] == "negative"


def test_complaint_without_rating_is_still_negative():
    assert label.label({"text": "국물이 다 새서 왔어요. 너무 별로였어요", "rating": None})["sentiment"] == "negative"
