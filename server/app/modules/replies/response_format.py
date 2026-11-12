"""POST /api/replies/rewrite 요청과 응답 모양."""

from pydantic import BaseModel, Field, field_validator

from app.review_reply_writer.write_reply_with_clova import RewriteStyle


class RewriteRequest(BaseModel):
    text: str = Field(min_length=1, max_length=1000, description="사장님이 보고 있는 지금 답글")
    style: RewriteStyle = Field(description="short(더 짧게) 또는 polite(더 정중하게)")
    plan_id: str | None = Field(None, description="답글 할 일 id. 있으면 근거 리뷰를 참고해서 다시 쓴다")

    @field_validator("text")
    @classmethod
    def not_blank(cls, value: str) -> str:
        """빈 글(공백만 있는 글)은 다시 쓸 것이 없다. 받으면 모델이 손님 말투로 새 글을 지어낸다."""
        if not value.strip():
            raise ValueError("다시 쓸 답글이 비어 있어요.")
        return value


class RewriteResponse(BaseModel):
    text: str  # 다시 쓴 답글
