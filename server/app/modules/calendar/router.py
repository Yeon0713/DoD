"""우리 매장 달력 API.

GET /api/calendar?from=2026-11-16&to=2026-11-22   날짜 × 시간대별 수요 신호와 이유 (오늘부터 35일까지 있음)
    store_id 를 붙이면 다른 가게 (비우면 서버 설정 DEMO_STORE_ID)
"""

import datetime as dt

from fastapi import APIRouter, Depends, Query

from app.core.error_response import check_date_range
from app.data_pipeline.store_selection import store_id_param
from app.modules.calendar.data_provider import get_calendar
from app.modules.calendar.response_format import CalendarResponse

router = APIRouter()


@router.get("", response_model=CalendarResponse, summary="날짜 × 시간대별 수요 신호")
def calendar(
    from_date: dt.date | None = Query(None, alias="from", description="시작 날짜(포함). 예) 2026-11-16"),
    to_date: dt.date | None = Query(None, alias="to", description="끝 날짜(포함). 예) 2026-11-22"),
    store_id: str = Depends(store_id_param),
):
    check_date_range(from_date, to_date)
    return get_calendar(store_id, from_date, to_date)
