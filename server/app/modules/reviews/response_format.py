"""GET /api/reviews 응답 모양."""

import datetime as dt

from pydantic import BaseModel

from app.planner.data_shapes import Review


class ReviewForScreen(Review):
    """계획 엔진의 리뷰 모양에 화면용 칸을 더한다."""

    ordered_at: dt.datetime | None = None  # 리뷰가 달린 주문의 주문 시각. 점검 화면이 '언제 늦었는지' 보여 줄 때 쓴다


class ReviewsResponse(BaseModel):
    is_example: bool  # true 면 contracts/sample_responses 의 예시 데이터
    reviews: list[ReviewForScreen]  # 리뷰와 분류 결과(label). 카드의 근거 리뷰를 펼칠 때 쓴다
