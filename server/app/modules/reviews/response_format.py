"""GET /api/reviews 응답 모양."""

from pydantic import BaseModel

from app.planner.data_shapes import Review


class ReviewsResponse(BaseModel):
    is_example: bool  # true 면 contracts/sample_responses 의 예시 데이터
    reviews: list[Review]  # 리뷰와 분류 결과(label). 카드의 근거 리뷰를 펼칠 때 쓴다
