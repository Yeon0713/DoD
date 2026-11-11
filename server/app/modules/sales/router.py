"""매출 API.

GET /api/sales?from=2026-11-02&to=2026-11-15&grain=weekday_daypart
    grain: day(하루), week(한 주), month(한 달), weekday_daypart(요일 × 시간대 평균)

매출 탭 화면용 (앱 06-70 ~ 06-75). period: today(오늘), week(이번 주), 4w(지난 4주), month(이번 달)
GET /api/sales/live                  오늘 실시간
GET /api/sales/weeks                 이번 주와 지난주
GET /api/sales/menus?period=week     메뉴별
GET /api/sales/times?period=4w       시간대와 요일
GET /api/sales/channels?period=week  어디서(홀/배달), 누가(단골/새 손님)
GET /api/sales/months                달별

모두 store_id 를 붙이면 다른 가게 (비우면 서버 설정 DEMO_STORE_ID).
앱이 보내는 now 값은 받기만 하고 쓰지 않는다. 서버는 언제나 실제 지금 시각으로 계산한다.
"""

import datetime as dt

from fastapi import APIRouter, Depends, Query

from app.core.error_response import check_date_range
from app.data_pipeline.store_selection import store_id_param
from app.modules.sales import dashboard_data_provider as dashboard
from app.modules.sales.dashboard_response_format import (
    SalesChannels,
    SalesLive,
    SalesMenus,
    SalesMonths,
    SalesPeriod,
    SalesTimes,
    SalesWeeks,
)
from app.modules.sales.data_provider import get_sales
from app.modules.sales.response_format import Grain, SalesResponse

router = APIRouter()

PERIOD = Query("week", description="today(오늘), week(이번 주), 4w(지난 4주), month(이번 달)")


@router.get("", response_model=SalesResponse, summary="매출 패턴")
def sales(
    from_date: dt.date | None = Query(None, alias="from", description="시작 날짜(포함). 예) 2026-11-02"),
    to_date: dt.date | None = Query(None, alias="to", description="끝 날짜(포함). 예) 2026-11-15"),
    grain: Grain = Query("day", description="묶는 단위"),
    store_id: str = Depends(store_id_param),
):
    check_date_range(from_date, to_date)
    return get_sales(store_id, from_date, to_date, grain)


@router.get("/live", response_model=SalesLive, summary="오늘 실시간 매출")
def sales_live(store_id: str = Depends(store_id_param)):
    return dashboard.get_live(store_id)


@router.get("/weeks", response_model=SalesWeeks, summary="이번 주와 지난주")
def sales_weeks(store_id: str = Depends(store_id_param)):
    return dashboard.get_weeks(store_id)


@router.get("/menus", response_model=SalesMenus, summary="메뉴별 매출")
def sales_menus(period: SalesPeriod = PERIOD, store_id: str = Depends(store_id_param)):
    return dashboard.get_menus(store_id, period)


@router.get("/times", response_model=SalesTimes, summary="시간대와 요일별 매출")
def sales_times(period: SalesPeriod = PERIOD, store_id: str = Depends(store_id_param)):
    return dashboard.get_times(store_id, period)


@router.get("/channels", response_model=SalesChannels, summary="어디서, 누가 샀나")
def sales_channels(period: SalesPeriod = PERIOD, store_id: str = Depends(store_id_param)):
    return dashboard.get_channels(store_id, period)


@router.get("/months", response_model=SalesMonths, summary="달별 매출")
def sales_months(store_id: str = Depends(store_id_param)):
    return dashboard.get_months(store_id)
