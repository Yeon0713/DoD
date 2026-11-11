"""답글 API.

POST /api/replies/rewrite   답글 다시 쓰기 (더 짧게 / 더 정중하게)
    요청 예) {"text": "지금 답글", "style": "short", "plan_id": "REVISIT_REPLY:rv_327:2026-11-14"}
    store_id 를 붙이면 다른 가게 (비우면 서버 설정 DEMO_STORE_ID)

답글 초안 자체는 GET /api/plan 의 할 일마다 draft_text 로 실려 간다.
"""

from fastapi import APIRouter, Depends

from app.data_pipeline.store_selection import store_id_param
from app.modules.replies.data_provider import rewrite_reply
from app.modules.replies.response_format import RewriteRequest, RewriteResponse

router = APIRouter()


@router.post("/rewrite", response_model=RewriteResponse, summary="답글 다시 쓰기 (더 짧게 / 더 정중하게)")
def rewrite(request: RewriteRequest, store_id: str = Depends(store_id_param)):
    return rewrite_reply(store_id, request)
