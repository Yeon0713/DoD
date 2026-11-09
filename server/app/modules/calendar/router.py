"""우리 매장 달력 API.

GET /api/calendar?from=2026-11-16&to=2026-11-22   날짜 × 시간대별 수요 신호와 이유
"""

import datetime as dt

from fastapi import APIRouter, Query

from app.core.error_response import check_date_range
from app.modules.calendar.data_provider import get_calendar
from app.modules.calendar.response_format import CalendarResponse

router = APIRouter()


@router.get("", response_model=CalendarResponse, summary="날짜 × 시간대별 수요 신호")
def calendar(
    from_date: dt.date | None = Query(None, alias="from", description="시작 날짜(포함). 예) 2026-11-16"),
    to_date: dt.date | None = Query(None, alias="to", description="끝 날짜(포함). 예) 2026-11-22"),
):
    check_date_range(from_date, to_date)
    return get_calendar(from_date, to_date)
