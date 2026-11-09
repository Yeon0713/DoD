"""매출 패턴 API.

GET /api/sales?from=2026-11-02&to=2026-11-15&grain=weekday_daypart
    grain: day(하루), week(한 주), month(한 달), weekday_daypart(요일 × 시간대 평균)
"""

import datetime as dt

from fastapi import APIRouter, Query

from app.core.error_response import check_date_range
from app.modules.sales.data_provider import get_sales
from app.modules.sales.response_format import Grain, SalesResponse

router = APIRouter()


@router.get("", response_model=SalesResponse, summary="매출 패턴")
def sales(
    from_date: dt.date | None = Query(None, alias="from", description="시작 날짜(포함). 예) 2026-11-02"),
    to_date: dt.date | None = Query(None, alias="to", description="끝 날짜(포함). 예) 2026-11-15"),
    grain: Grain = Query("day", description="묶는 단위"),
):
    check_date_range(from_date, to_date)
    return get_sales(from_date, to_date, grain)
