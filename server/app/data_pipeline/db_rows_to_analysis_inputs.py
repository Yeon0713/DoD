"""DB 행(지호) → 태성 분석 입력(AnalysisInputs) 번역.

내용은 바꾸지 않고 표현만 맞춘다.
- id 는 글자로: 주문·메뉴·근무는 "1", 리뷰는 rv_001, 행사는 event_001, 경기는 game_001, 알바는 staff_001
- 코드값은 대문자로: hall → HALL, main → MAIN. 행사·경기 종류는 태성의 mock_csv_reader 규칙을 그대로 쓴다
- 칸 이름 맞추기: content → text, name → title, starts_at → start_at, precip_mm → rain_mm
- 알바 이름은 분석에 넘기지 않는다 (인건비 계산에는 시간과 시급만 필요하다). 이름은 staff API 가 화면에 보낸다
- 리뷰 플랫폼: DB 에 칸이 없어서, 배달 주문과 이어진 리뷰는 BAEMIN, 나머지(주문 없는 방문 리뷰)는 NAVER 로 정한다 [임시 규칙]
- 행사 거리: DB 의 distance_km 는 가게마다 다를 수 없는 한 숫자라서, 행사 위치와 가게 위치로 가게마다 다시 잰다
- 시간대: 분석 기본값(아침/점심/저녁) 대신 앱과 계획 엔진이 쓰는 점심/저녁/밤으로 나눠 넘긴다 (sales_dayparts)
"""

import datetime as dt
import math

from app.analysis.input_shapes import (
    AnalysisInputs,
    DaypartRange,
    Menu,
    Order,
    OrderItem,
    Shift,
    StoreInfo,
    WeatherDay,
)
from app.analysis.mock_csv_reader import event_kind, game_kind
from app.data_pipeline import read_store_db
from app.planner.data_shapes import Event, Game, Platform, Review

# 점심/저녁/밤 경계. 앱 매출 화면과 같은 기준이다 (점심 15시 전, 저녁 15~20시, 밤 20시 뒤)
LUNCH_END = dt.time(15, 0)
DINNER_END = dt.time(20, 0)
DAY_MINUTES = 24 * 60
EARTH_RADIUS_KM = 6371.0


# ── 표현 바꾸기 ──


def review_id_of(db_review_id: int) -> str:
    """1 → rv_001"""
    return f"rv_{db_review_id:03d}"


def event_id_of(db_event_id: int) -> str:
    """1 → event_001"""
    return f"event_{db_event_id:03d}"


def game_id_of(db_game_id: int) -> str:
    """1 → game_001"""
    return f"game_{db_game_id:03d}"


def staff_key_of(db_staff_id: int) -> str:
    """1 → staff_001"""
    return f"staff_{db_staff_id:03d}"


def review_platform(order_channel: str | None) -> Platform:
    """배달 주문과 이어진 리뷰는 배민, 나머지는 네이버 [임시 규칙. DB 에 플랫폼 칸이 생기면 그 값을 쓴다]"""
    return "BAEMIN" if order_channel == "delivery" else "NAVER"


def distance_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """두 위치 사이 거리(km). 지구를 공으로 보고 잰다(하버사인 공식)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    d_lat, d_lng = p2 - p1, math.radians(lng2 - lng1)
    a = math.sin(d_lat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(d_lng / 2) ** 2
    return round(2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a)), 2)


def _minutes(t: dt.time) -> int:
    return t.hour * 60 + t.minute


def _time(minutes: int) -> dt.time:
    minutes %= DAY_MINUTES
    return dt.time(minutes // 60, minutes % 60)


def sales_dayparts(open_time: dt.time, close_time: dt.time) -> list[DaypartRange]:
    """영업시간을 점심(~15시)·저녁(15~20시)·밤(20시~)으로 나눈다. 영업시간과 겹치지 않는 시간대는 뺀다.

    예) 10:00~22:00 → 점심 10~15, 저녁 15~20, 밤 20~22
        17:00~03:00 → 저녁 17~20, 밤 20~03 (자정을 넘는다)
    """
    open_at = _minutes(open_time)
    close_at = _minutes(close_time) + (DAY_MINUTES if close_time < open_time else 0)
    lunch_end, dinner_end = _minutes(LUNCH_END), _minutes(DINNER_END)
    bounds = [
        ("LUNCH", open_at, min(lunch_end, close_at)),
        ("DINNER", max(open_at, lunch_end), min(dinner_end, close_at)),
        ("NIGHT", max(open_at, dinner_end), close_at),
    ]
    return [DaypartRange(daypart=name, start=_time(s), end=_time(e)) for name, s, e in bounds if s < e]


# ── 테이블별 번역 ──


def to_store_info(store: dict) -> StoreInfo:
    return StoreInfo(
        store_id=store["store_id"],
        name=store["name"],
        lat=store["lat"],
        lng=store["lng"],
        open_time=store["open_time"],
        close_time=store["close_time"],
        closed_weekdays=store["closed_weekdays"] or [],
        dayparts=sales_dayparts(store["open_time"], store["close_time"]),
    )


def to_order(row: dict) -> Order:
    return Order(
        order_id=str(row["order_id"]),
        ordered_at=row["ordered_at"],
        channel=row["channel"].upper(),
        customer_key=row["customer_key"] or None,
        total_amount=row["total_amount"],
    )


def to_order_item(row: dict) -> OrderItem:
    return OrderItem(
        order_id=str(row["order_id"]),
        menu_id=str(row["menu_id"]),
        quantity=row["quantity"],
        unit_price=row["unit_price"],
    )


def to_menu(row: dict) -> Menu:
    return Menu(menu_id=str(row["menu_id"]), name=row["name"], category=row["category"].upper(), price=row["price"])


def to_shift(row: dict, hourly_wage: int) -> Shift:
    return Shift(
        shift_id=str(row["shift_id"]),
        staff_key=staff_key_of(row["staff_id"]),
        starts_at=row["starts_at"],
        ends_at=row["ends_at"],
        hourly_wage=hourly_wage,
    )


def to_review(row: dict) -> Review:
    """분류 결과(label)는 비워 둔다. 태성의 리뷰 분류가 채운다."""
    return Review(
        review_id=review_id_of(row["review_id"]),
        platform=row.get("platform") or review_platform(row.get("order_channel")),
        written_at=row["written_at"],
        rating=row["rating"],
        text=row["content"],
        customer_key=row["customer_key"] or None,
        order_id=str(row["order_id"]) if row["order_id"] is not None else None,
    )


def to_event(row: dict, store: dict) -> Event:
    return Event(
        event_id=event_id_of(row["event_id"]),
        kind=event_kind(row["kind"]),
        title=row["name"],
        start_at=row["starts_at"],
        end_at=row["ends_at"],
        distance_km=distance_km(store["lat"], store["lng"], row["lat"], row["lng"]),
    )


def to_games(rows: list[dict]) -> list[Game]:
    """모르는 종목은 경기 종류 코드값이 없어서 건너뛴다 (태성 규칙과 같다)."""
    games = []
    for row in rows:
        kind = game_kind(row["sport"], row["level"])
        if kind is not None:
            games.append(Game(game_id=game_id_of(row["game_id"]), kind=kind, title=row["title"], start_at=row["starts_at"]))
    return games


def to_weather(row: dict) -> WeatherDay:
    return WeatherDay(
        date=row["date"],
        temp_max=float(row["temp_max"]),
        temp_min=float(row["temp_min"]),
        rain_mm=float(row["precip_mm"]),
    )


# ── 한 가게 전체 ──


def build_analysis_inputs(store_id: str, now: dt.datetime) -> AnalysisInputs:
    """DB 에서 한 가게의 now 까지 데이터를 꺼내 태성 분석 입력 하나로 묶는다."""
    store = read_store_db.read_store(store_id)
    wages = {row["staff_id"]: row["hourly_wage"] for row in read_store_db.read_staff(store_id)}
    return AnalysisInputs(
        store=to_store_info(store),
        orders=[to_order(row) for row in read_store_db.read_orders(store_id, now)],
        order_items=[to_order_item(row) for row in read_store_db.read_order_items(store_id, now)],
        menus=[to_menu(row) for row in read_store_db.read_menus(store_id)],
        shifts=[to_shift(row, wages[row["staff_id"]]) for row in read_store_db.read_shifts(store_id, now)],
        events=[to_event(row, store) for row in read_store_db.read_events()],
        games=to_games(read_store_db.read_games()),
        weather=[to_weather(row) for row in read_store_db.read_weather()],
        reviews=[to_review(row) for row in read_store_db.read_reviews(store_id, now)],
    )


def inputs_until(full: AnalysisInputs, now: dt.datetime) -> AnalysisInputs:
    """build_analysis_inputs(store_id, 늦은 시각) 로 한 번 읽어 둔 입력에서 now 까지 생긴 것만 남긴다.

    build_analysis_inputs(store_id, now) 와 같은 결과다 (주문·근무는 시작 시각, 리뷰는 쓴 시각, 주문 메뉴는 그 주문의 시각으로 자른다).
    여러 시각을 차례로 계산할 때(개발자 대시보드 시연 훑기) DB 를 시각마다 다시 읽지 않으려고 쓴다.
    """
    orders = [order for order in full.orders if order.ordered_at <= now]
    kept = {order.order_id for order in orders}
    return full.model_copy(
        update={
            "orders": orders,
            "order_items": [item for item in full.order_items if item.order_id in kept],
            "shifts": [shift for shift in full.shifts if shift.starts_at <= now],
            "reviews": [review for review in full.reviews if review.written_at <= now],
        }
    )

