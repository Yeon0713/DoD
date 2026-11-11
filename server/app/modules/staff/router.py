"""알바 API.

GET /api/staff                                   알바 목록 (이름, 시급)
GET /api/staff/shifts?from=2026-11-09&to=2026-11-12   근무 기록. 기간을 비우면 이번 주 월요일 ~ 오늘
    store_id 를 붙이면 다른 가게 (비우면 서버 설정 DEMO_STORE_ID)
"""

import datetime as dt

from fastapi import APIRouter, Depends, Query

from app.core.error_response import check_date_range
from app.data_pipeline.store_selection import store_id_param
from app.modules.staff.data_provider import get_shifts, get_staff
from app.modules.staff.response_format import ShiftsResponse, StaffResponse

router = APIRouter()


@router.get("", response_model=StaffResponse, summary="알바 목록")
def staff(store_id: str = Depends(store_id_param)):
    return get_staff(store_id)


@router.get("/shifts", response_model=ShiftsResponse, summary="근무 기록")
def shifts(
    from_date: dt.date | None = Query(None, alias="from", description="시작 날짜(포함). 예) 2026-11-09"),
    to_date: dt.date | None = Query(None, alias="to", description="끝 날짜(포함). 예) 2026-11-12"),
    store_id: str = Depends(store_id_param),
):
    check_date_range(from_date, to_date)
    return get_shifts(store_id, from_date, to_date)
