"""POST /api/replies/rewrite 요청과 응답 모양."""

from pydantic import BaseModel, Field

from app.review_reply_writer.write_reply_with_clova import RewriteStyle


class RewriteRequest(BaseModel):
    text: str = Field(min_length=1, max_length=1000, description="사장님이 보고 있는 지금 답글")
    style: RewriteStyle = Field(description="short(더 짧게) 또는 polite(더 정중하게)")
    plan_id: str | None = Field(None, description="답글 할 일 id. 있으면 근거 리뷰를 참고해서 다시 쓴다")


class RewriteResponse(BaseModel):
    text: str  # 다시 쓴 답글
