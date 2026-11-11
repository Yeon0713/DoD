"""오늘의 카드 API.

GET /api/today              오늘 알림 시각별 카드 묶음
GET /api/today?store_id=s003   다른 가게 (비우면 서버 설정 DEMO_STORE_ID)
"""

from fastapi import APIRouter, Depends

from app.data_pipeline.store_selection import store_id_param
from app.modules.today.data_provider import get_today
from app.modules.today.response_format import TodayResponse

router = APIRouter()


@router.get("", response_model=TodayResponse, summary="오늘 알림 시각별 카드 묶음")
def today(store_id: str = Depends(store_id_param)):
    return get_today(store_id)
