"""네이버 플레이스 대신 API.

GET /api/naver/place   가게 정보 불러오기 (처음 쓰는 날, 설정 > 네이버 다시 불러오기)
    네이버 공개 API 가 없어서 DB 가게 정보를 같은 모양으로 돌려준다.
    store_id 를 붙이면 다른 가게 (비우면 서버 설정 DEMO_STORE_ID)
"""

from fastapi import APIRouter, Depends

from app.data_pipeline.store_selection import store_id_param
from app.modules.naver.data_provider import get_place
from app.modules.naver.response_format import NaverPlaceResponse

router = APIRouter()


@router.get("/place", response_model=NaverPlaceResponse, summary="가게 정보 불러오기 (DB 로 대신)")
def place(store_id: str = Depends(store_id_param)):
    return get_place(store_id)
