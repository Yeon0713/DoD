"""어느 가게를 보여 줄지 정한다.

지금은 로그인이 없어서 서버 설정(DEMO_STORE_ID, 기본 s001)의 가게를 보여 주고,
주소에 ?store_id=s002 를 붙이면 그 가게를 보여 준다.
로그인이 생기면 이 파일에서 '로그인한 사장님의 가게'로 바꾸고, 다른 가게는 막는다.
"""

from fastapi import Query

from app.core.config import settings
from app.core.error_response import ApiError
from app.data_pipeline.read_store_db import list_store_ids


def resolve_store_id(requested: str | None) -> str:
    store_id = requested or settings.demo_store_id
    if store_id not in list_store_ids():
        raise ApiError(404, "STORE_NOT_FOUND", f"{store_id} 가게가 없어요. 있는 가게: {', '.join(list_store_ids())}")
    return store_id


def store_id_param(
    store_id: str | None = Query(None, description="볼 가게. 비우면 서버 설정(DEMO_STORE_ID) 가게. 예) s002"),
) -> str:
    """라우터에서 Depends(store_id_param) 으로 쓴다."""
    return resolve_store_id(store_id)
