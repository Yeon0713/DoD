"""분석에 넣는 입력 모양. 목업 CSV 든 DB 든 이 모양으로 바꿔서 넣는다.

행사, 경기, 리뷰는 계획 엔진(app/planner/data_shapes.py)의 Event, Game, Review 를 그대로 쓴다.
분석 결과의 근거 id(ref_id, review_ids)와 계획 엔진에 넘기는 id 가 같아야 하기 때문이다.

모든 시각은 시간대가 붙어 있어야 한다(계약: +09:00 이 붙은 ISO 8601). 시간대 없는(naive) 시각은
컴퓨터의 시스템 시간대로 해석돼 서버마다 칸이 달라지므로 서울 시각으로 바꿔 주지 않고 거절한다.
"""

import datetime as dt

from pydantic import AwareDatetime, BaseModel, model_validator

from app.analysis.result_shapes import AnalysisDaypart
from app.planner.data_shapes import Event, Game, Review, Weekday


class DaypartRange(BaseModel):
    """시간대 하나의 시작과 끝. [start, end) 이다."""

    daypart: AnalysisDaypart
    start: dt.time
    end: dt.time

    @model_validator(mode="after")
    def _start_before_end(self):
        if self.start >= self.end:
            raise ValueError("시간대 시작이 끝보다 빨라야 합니다.")
        return self


class StoreInfo(BaseModel):
    """분석에 쓰는 매장 정보. 마감은 같은 날 안이다(자정을 넘기지 않는다)."""

    store_id: str
    name: str
    lat: float
    lng: float
    open_time: dt.time
    close_time: dt.time
    closed_weekdays: list[Weekday] = []
    dayparts: list[DaypartRange] | None = None  # 사장님이 정한 시간대. 없으면 기본 경계를 쓴다

    @model_validator(mode="after")
    def _open_before_close(self):
        if self.open_time >= self.close_time:
            raise ValueError("영업 시작이 마감보다 빨라야 합니다.")
        return self


class Order(BaseModel):
    order_id: str
    ordered_at: AwareDatetime
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
    starts_at: AwareDatetime
    ends_at: AwareDatetime
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

    @model_validator(mode="after")
    def _shared_times_are_aware(self):
        """계획 엔진 모양(Event, Game, Review)은 naive 시각도 받으므로 여기서 막는다."""
        times = [
            *((f"events[{e.event_id}].start_at", e.start_at) for e in self.events),
            *((f"events[{e.event_id}].end_at", e.end_at) for e in self.events),
            *((f"games[{g.game_id}].start_at", g.start_at) for g in self.games),
            *((f"reviews[{r.review_id}].written_at", r.written_at) for r in self.reviews),
        ]
        for name, t in times:
            require_aware(t, name)
        return self


def require_aware(t: dt.datetime, name: str = "now") -> None:
    """시간대 없는(naive) 시각이면 ValueError."""
    if t.tzinfo is None or t.utcoffset() is None:
        raise ValueError(f"{name} 에 시간대가 없습니다(+09:00 을 붙여야 합니다): {t.isoformat()}")
