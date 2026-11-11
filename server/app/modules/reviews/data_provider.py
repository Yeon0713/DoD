"""리뷰와 분류 결과 가져오기.

DB 리뷰(지호) → 태성 리뷰 분류(키워드 규칙)가 붙은 리뷰를 조건에 맞게 골라 돌려준다.
리뷰 플랫폼은 DB 에 칸이 없어 배달 주문과 이어진 리뷰는 BAEMIN, 나머지는 NAVER 로 정했다 (db_rows_to_analysis_inputs).
"""

import datetime as dt

from app.core.seoul_time import is_within_dates, to_seoul
from app.data_pipeline.store_snapshot_cache import get_snapshot
from app.modules.reviews.response_format import ReviewForScreen, ReviewsResponse


def get_reviews(store_id: str, from_date: dt.date | None, to_date: dt.date | None, quick: bool | None) -> ReviewsResponse:
    snapshot = get_snapshot(store_id)
    reviews = [
        ReviewForScreen(
            **review.model_dump(),
            ordered_at=snapshot.ordered_at_by_order.get(review.order_id) if review.order_id else None,
        )
        for review in snapshot.reviews
        if is_within_dates(to_seoul(review.written_at).date(), from_date, to_date)
        and (quick is None or (review.label is not None and review.label.is_quick) == quick)
    ]
    return ReviewsResponse(is_example=False, reviews=reviews)
