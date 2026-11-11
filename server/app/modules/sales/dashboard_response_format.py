"""매출 탭(앱 06-70 ~ 06-75) 응답 모양. 앱의 mobile/src/types/sales.ts 와 칸 이름이 같다.

GET /api/sales/live       오늘 실시간
GET /api/sales/weeks      이번 주와 지난주
GET /api/sales/menus      메뉴별
GET /api/sales/times      시간대와 요일
GET /api/sales/channels   어디서(홀/배달), 누가(단골/새 손님)
GET /api/sales/months     달별
"""

import datetime as dt
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SalesPeriod = Literal["today", "week", "4w", "month"]  # 오늘, 이번 주, 지난 4주, 이번 달
ScreenDaypart = Literal["LUNCH", "DINNER", "NIGHT"]


class HourAmount(BaseModel):
    hour: int  # 0~23시
    amount: int  # 오늘 그 시간 매출
    usual: int  # 지난 4주 같은 요일 그 시간 평균
    state: Literal["past", "now", "future"]


class SalesLive(BaseModel):
    is_example: bool
    now: dt.datetime
    date: dt.date  # 영업일
    amount: int  # 오늘 지금까지 매출
    orders: int
    avg: int  # 주문 1번 평균
    yesterdaySame: int  # 어제 같은 시각까지
    usualDay: int  # 지난 4주 같은 요일 하루 평균
    usualSame: int  # 지난 4주 같은 요일 같은 시각까지 평균
    hourly: list[HourAmount]


class WeekDay(BaseModel):
    date: dt.date
    amount: int  # 지난날은 실제, 오늘은 지금까지, 앞날은 예상
    last: int  # 지난주 같은 요일 실제
    state: Literal["actual", "now", "forecast"]
    reasons: list[str]  # 달력 이유 이름. 예) ["축제", "추워져요"]
    usual: int | None = None  # 오늘만: 지난 4주 같은 요일 평균


class SalesWeeks(BaseModel):
    is_example: bool
    weekStart: dt.date  # 이번 주 월요일
    days: list[WeekDay]
    toDate: int  # 이번 주 지금까지
    lastSamePeriod: int  # 지난주 같은 때까지
    lastTotal: int  # 지난주 전체
    forecastTotal: int  # 이번 주 지금까지 + 남은 날 예상


class PeriodRange(BaseModel):
    """기간이 있는 응답의 공통 칸. 'from' 은 파이썬 예약어라 코드에서는 from_ 으로 쓰고 응답에는 from 으로 나간다."""

    model_config = ConfigDict(populate_by_name=True)

    is_example: bool
    period: SalesPeriod
    from_: dt.date = Field(alias="from")
    to: dt.date


class MenuAmount(BaseModel):
    name: str
    qty: int
    amount: int
    prevQty: int  # 바로 앞 같은 길이 기간
    prevAmount: int


class SalesMenus(PeriodRange):
    items: list[MenuAmount]


class DaypartAmount(BaseModel):
    key: ScreenDaypart
    label: str  # 점심, 저녁, 밤
    range: str  # 예) "10시 ~ 15시". 영업하지 않는 시간대면 빈 글자
    amount: int


class WeekdayDaypartAverage(BaseModel):
    weekday: int  # 0=월 ~ 6=일
    daypart: ScreenDaypart
    avg: int  # 지난 4주 하루 평균


class SalesTimes(PeriodRange):
    dayparts: list[DaypartAmount]
    grid: list[WeekdayDaypartAverage]


class ChannelAmount(BaseModel):
    key: str  # HALL, DELIVERY
    label: str
    amount: int
    orders: int


class PeopleAmount(BaseModel):
    people: int
    amount: int


class CustomerSplit(BaseModel):
    regular: PeopleAmount  # 태성 분석이 매주·매달 단골로 판정한 손님
    fresh: PeopleAmount  # 이 기간에 처음 주문한 손님
    other: PeopleAmount  # 그 밖에 손님 키가 있는 손님
    unknownOrders: int  # 손님 키가 없는 주문 (홀 현금 결제 등)
    unknownAmount: int


class SalesChannels(PeriodRange):
    channels: list[ChannelAmount]
    platformsSimulated: bool  # 배달앱별로 나눈 값을 지어냈는지. DB 에는 홀/배달만 있어서 나누지 않고 false
    customers: CustomerSplit


class MonthAmount(BaseModel):
    month: str  # "2026-11"
    amount: int
    orders: int
    days: int  # 매출을 센 날 수
    partial: bool  # 이번 달이거나 달 중간부터 기록이 있는 달
    forecast: int | None = None  # 이번 달만: 지금까지 + 남은 날 × 하루 평균


class SalesMonths(BaseModel):
    is_example: bool
    months: list[MonthAmount]
    avgDaily: int  # 지난 28일 하루 평균
    avgOrder: int  # 지난 28일 주문 1번 평균
