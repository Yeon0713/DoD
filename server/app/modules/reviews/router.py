"""리뷰 API.

GET /api/reviews?from=2026-11-16&to=2026-11-22&quick=true   리뷰와 분류 결과
"""

import datetime as dt

from fastapi import APIRouter, Query

from app.core.error_response import check_date_range
from app.modules.reviews.data_provider import get_reviews
from app.modules.reviews.response_format import ReviewsResponse

router = APIRouter()


@router.get("", response_model=ReviewsResponse, summary="리뷰와 분류 결과")
def reviews(
    from_date: dt.date | None = Query(None, alias="from", description="시작 날짜(포함). 예) 2026-11-16"),
    to_date: dt.date | None = Query(None, alias="to", description="끝 날짜(포함). 예) 2026-11-22"),
    quick: bool | None = Query(None, description="true 면 불만 리뷰(빠른 응대)만, false 면 나머지만"),
):
    check_date_range(from_date, to_date)
    return get_reviews(from_date, to_date, quick)
