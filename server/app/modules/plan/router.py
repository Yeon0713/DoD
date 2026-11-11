"""할 일 목록 API.

GET /api/plan?from=2026-11-16&to=2026-11-22   기간 안의 할 일과 승인 없는 알림
    store_id 를 붙이면 다른 가게 (비우면 서버 설정 DEMO_STORE_ID)
"""

import datetime as dt

from fastapi import APIRouter, Depends, Query

from app.core.error_response import check_date_range
from app.data_pipeline.store_selection import store_id_param
from app.modules.plan.data_provider import get_plan
from app.modules.plan.response_format import PlanResponse

router = APIRouter()


@router.get("", response_model=PlanResponse, summary="기간 안의 할 일과 알림")
def plan(
    from_date: dt.date | None = Query(None, alias="from", description="시작 날짜(포함). 예) 2026-11-16"),
    to_date: dt.date | None = Query(None, alias="to", description="끝 날짜(포함). 예) 2026-11-22"),
    store_id: str = Depends(store_id_param),
):
    check_date_range(from_date, to_date)
    return get_plan(store_id, from_date, to_date)
