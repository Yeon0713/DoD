"""분석에 넣는 입력 모양. 목업 CSV 든 DB 든 이 모양으로 바꿔서 넣는다.

행사, 경기, 리뷰는 계획 엔진(app/planner/data_shapes.py)의 Event, Game, Review 를 그대로 쓴다.
분석 결과의 근거 id(ref_id, review_ids)와 계획 엔진에 넘기는 id 가 같아야 하기 때문이다.
"""

import datetime as dt

from pydantic import BaseModel, model_validator

from app.analysis.result_shapes import AnalysisDaypart
from app.planner.data_shapes import Event, Game, Review, Weekday


class DaypartRange(BaseModel):
    """시간대 하나의 시작과 끝. [start, end) 이다. 끝이 시작보다 이르면 자정을 넘는다. 예) 17:00~03:00"""

    daypart: AnalysisDaypart
    start: dt.time
    end: dt.time

    @model_validator(mode="after")
    def _start_not_end(self):
        if self.start == self.end:
            raise ValueError("시간대 시작과 끝이 같을 수 없습니다.")
        return self


class StoreInfo(BaseModel):
    """분석에 쓰는 매장 정보.

    마감이 오픈보다 이르면 자정을 넘겨 다음 날 새벽에 마감한다. 예) 17:00~03:00
    그런 매장은 영업일 기준으로 센다. 마감 전 새벽 주문(1/2 01:00)은 전날(1/1) 영업일이다.
    """

    store_id: str
    name: str
    lat: float
    lng: float
    open_time: dt.time
    close_time: dt.time
    closed_weekdays: list[Weekday] = []
    dayparts: list[DaypartRange] | None = None  # 사장님이 정한 시간대. 없으면 기본 경계를 쓴다

    @model_validator(mode="after")
    def _open_not_close(self):
        if self.open_time == self.close_time:
            raise ValueError("영업 시작과 마감이 같을 수 없습니다.")
        return self

    @property
    def overnight(self) -> bool:
        """자정을 넘겨 다음 날 새벽에 마감하는지."""
        return self.close_time < self.open_time


class Order(BaseModel):
    order_id: str
    ordered_at: dt.datetime
    channel: str  # HALL, DELIVERY, BAEMIN 같은 대문자 코드값
    customer_key: str | None = None
    total_amount: int


class OrderItem(BaseModel):
    order_id: str
    menu_id: str
    quantity: int
    unit_price: int


class Menu(BaseModel):
    menu_id: str
    name: str
    category: str  # MAIN, SIDE, DRINK
    price: int
    unit_cost: int | None = None  # 메뉴 원가. 데이터가 없으면 None


class Shift(BaseModel):
    """근무 한 번. 직원 이름은 다루지 않고 staff_key 만 쓴다."""

    shift_id: str
    staff_key: str
    starts_at: dt.datetime
    ends_at: dt.datetime
    hourly_wage: int


class WeatherDay(BaseModel):
    """하루 날씨. 지난날은 관측, 앞날은 예보로 본다."""

    date: dt.date
    temp_max: float
    temp_min: float
    rain_mm: float


class AnalysisInputs(BaseModel):
    store: StoreInfo
    orders: list[Order] = []
    order_items: list[OrderItem] = []
    menus: list[Menu] = []
    shifts: list[Shift] = []
    events: list[Event] = []
    games: list[Game] = []
    weather: list[WeatherDay] = []
    reviews: list[Review] = []  # 분류 전 리뷰는 label 이 None
