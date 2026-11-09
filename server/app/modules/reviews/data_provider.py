"""리뷰와 분류 결과 가져오기.

지금은 응답 예시(reviews_response.example.json)에서 조건에 맞는 리뷰만 골라 돌려준다.
지호의 리뷰 데이터와 태성의 분류 결과(review_label)가 나오면 그걸 읽도록 바꾼다.
"""

import datetime as dt

from app.core.sample_response_loader import load_sample_response
from app.core.seoul_time import is_within_dates, to_seoul
from app.modules.reviews.response_format import ReviewsResponse


def get_reviews(from_date: dt.date | None, to_date: dt.date | None, quick: bool | None) -> ReviewsResponse:
    data = ReviewsResponse.model_validate(load_sample_response("reviews"))
    reviews = [
        review
        for review in data.reviews
        if is_within_dates(to_seoul(review.written_at).date(), from_date, to_date)
        and (quick is None or (review.label is not None and review.label.is_quick) == quick)
    ]
    return data.model_copy(update={"reviews": reviews})
