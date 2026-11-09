"""오늘의 카드 API.

GET /api/today   오늘 알림 시각별 카드 묶음
"""

from fastapi import APIRouter

from app.modules.today.data_provider import get_today
from app.modules.today.response_format import TodayResponse

router = APIRouter()


@router.get("", response_model=TodayResponse, summary="오늘 알림 시각별 카드 묶음")
def today():
    return get_today()
