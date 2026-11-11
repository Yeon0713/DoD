"""답글 다시 쓰기. 사장님이 '더 짧게', '더 정중하게'를 누르면 CLOVA X 가 바로 다시 쓴다.

plan_id 가 오면 그 답글의 근거 리뷰를 같이 넘겨서, 리뷰에 맞는 말을 남긴 채 고치게 한다.
CLOVA 키가 없거나 실패하면 오류를 돌려주고, 앱은 '다시 하기'를 보여 준다.
"""

from app.core.config import settings
from app.core.error_response import ApiError
from app.data_pipeline.store_snapshot_cache import get_snapshot
from app.modules.replies.response_format import RewriteRequest, RewriteResponse
from app.review_reply_writer.write_reply_with_clova import rewrite


def rewrite_reply(store_id: str, request: RewriteRequest) -> RewriteResponse:
    if not settings.clova_studio_api_key:
        raise ApiError(503, "CLOVA_NOT_CONFIGURED", "답글을 다시 쓰려면 서버에 CLOVA 키가 필요해요.")
    snapshot = get_snapshot(store_id)
    review = None
    if request.plan_id and snapshot.plan is not None:
        item = next((i for i in snapshot.plan.plan_items if i.plan_id == request.plan_id), None)
        if item is not None and item.basis.kind == "REVIEW":
            review = next((r for r in snapshot.reviews if r.review_id == item.basis.ref_id), None)
    text = rewrite(request.text, request.style, snapshot.store, review)
    if text is None:
        raise ApiError(502, "REWRITE_FAILED", "답글을 다시 쓰지 못했어요. 잠시 뒤 다시 해 주세요.")
    return RewriteResponse(text=text)
