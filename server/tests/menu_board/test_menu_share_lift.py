"""세부 종류별 메뉴 비중 변화 테스트. server/ 폴더에서 `python -m pytest` 로 실행한다.

가게: 11~22시, 시간대 점심 11~15 · 저녁 15~20 · 밤 20~22, 쉬는 날 없음. 메뉴 1 국수, 2 전, 3 신메뉴(팔린 적 없음).
"""

import datetime as dt
import itertools

import pytest

from app.analysis.input_shapes import AnalysisInputs, DaypartRange, Menu, Order, OrderItem, StoreInfo, WeatherDay
from app.core.seoul_time import SEOUL
from app.menu_board.menu_share_lift import menu_share_lift
from app.planner.data_shapes import Event, Game

STORE = StoreInfo(
    store_id="t001",
    name="테스트 국숫집",
    lat=37.0,
    lng=127.0,
    open_time=dt.time(11),
    close_time=dt.time(22),
    dayparts=[
        DaypartRange(daypart="LUNCH", start=dt.time(11), end=dt.time(15)),
        DaypartRange(daypart="DINNER", start=dt.time(15), end=dt.time(20)),
        DaypartRange(daypart="NIGHT", start=dt.time(20), end=dt.time(22)),
    ],
)
MENUS = [Menu(menu_id=m, name=n, category="MAIN", price=8000) for m, n in [("1", "국수"), ("2", "전"), ("3", "신메뉴")]]
LUNCH, DINNER = 12, 18  # 그 시간대에 드는 주문 시각

_order_ids = itertools.count(1)


def at(day: dt.date, hour: int) -> dt.datetime:
    return dt.datetime.combine(day, dt.time(hour), tzinfo=SEOUL)


def days(first: dt.date, last: dt.date) -> list[dt.date]:
    return [first + dt.timedelta(days=i) for i in range((last - first).days + 1)]


def sold(day: dt.date, hour: int, qty: dict[str, int]) -> tuple[list[Order], list[OrderItem]]:
    """그날 그 시각 주문 하나에 메뉴별 수량"""
    order_id = f"o{next(_order_ids)}"
    order = Order(order_id=order_id, ordered_at=at(day, hour), channel="HALL", total_amount=8000 * sum(qty.values()))
    items = [OrderItem(order_id=order_id, menu_id=m, quantity=q, unit_price=8000) for m, q in qty.items() if q]
    return [order], items


def inputs(sales, events=(), games=(), weather=()) -> AnalysisInputs:
    orders = [o for os_, _ in sales for o in os_]
    items = [i for _, is_ in sales for i in is_]
    return AnalysisInputs(store=STORE, orders=orders, order_items=items, menus=MENUS, events=list(events), games=list(games), weather=list(weather))


def festival(day: dt.date, start_hour: int = 11, end_hour: int = 15, event_id: str = "event_001") -> Event:
    return Event(event_id=event_id, kind="LOCAL_FESTIVAL", title="동네 축제", start_at=at(day, start_hour), end_at=at(day, end_hour), distance_km=0.5)


FESTIVAL_DAY = dt.date(2026, 10, 10)
AS_OF = dt.date(2026, 11, 1)


def usual_lunches(before: dt.date, weeks: int = 8) -> list:
    """before 전날부터 weeks 주 동안 매일 점심: 국수 3, 전 1 (75% : 25%)"""
    first = before - dt.timedelta(days=7 * weeks)
    return [sold(day, LUNCH, {"1": 3, "2": 1}) for day in days(first, before - dt.timedelta(days=1))]


def test_festival_lunch_share_change_in_percent_points():
    sales = [
        *usual_lunches(FESTIVAL_DAY),
        sold(FESTIVAL_DAY, LUNCH, {"1": 1, "2": 3}),  # 축제 점심: 25% : 75%
        sold(FESTIVAL_DAY, DINNER, {"1": 10}),  # 축제와 겹치지 않은 저녁은 보지 않는다
    ]
    lift = menu_share_lift(inputs(sales, events=[festival(FESTIVAL_DAY)]), "EVENT", "LOCAL_FESTIVAL", AS_OF)
    assert lift.n == 1
    assert lift.lift_pp == {"1": -50.0, "2": 50.0, "3": 0.0}  # 단위는 %p: 50.0 = 50%p. 신메뉴도 0.0 으로 들어간다


def test_needs_four_weeks_of_usual_orders():
    festival_lunch = sold(FESTIVAL_DAY, LUNCH, {"1": 1, "2": 3})
    three_weeks = menu_share_lift(inputs([*usual_lunches(FESTIVAL_DAY, weeks=3), festival_lunch], events=[festival(FESTIVAL_DAY)]), "EVENT", "LOCAL_FESTIVAL", AS_OF)
    four_weeks = menu_share_lift(inputs([*usual_lunches(FESTIVAL_DAY, weeks=4), festival_lunch], events=[festival(FESTIVAL_DAY)]), "EVENT", "LOCAL_FESTIVAL", AS_OF)
    assert three_weeks.n == 0
    assert three_weeks.lift_pp == {"1": 0.0, "2": 0.0, "3": 0.0}  # 쓸 날이 없어도 예외 없이 모두 0.0
    assert four_weeks.n == 1


def test_weeks_are_counted_after_removing_special_cells():
    # 4주 치 평소 점심 가운데 가장 먼 주(4주 전)는 매일 비가 와서 모두 특별한 칸이다 → 남는 주는 3주
    rainy = [WeatherDay(date=day, temp_max=15, temp_min=8, rain_mm=20) for day in days(FESTIVAL_DAY - dt.timedelta(days=28), FESTIVAL_DAY - dt.timedelta(days=22))]
    sales = [*usual_lunches(FESTIVAL_DAY, weeks=4), sold(FESTIVAL_DAY, LUNCH, {"1": 1, "2": 3})]
    lift = menu_share_lift(inputs(sales, events=[festival(FESTIVAL_DAY)], weather=rainy), "EVENT", "LOCAL_FESTIVAL", AS_OF)
    assert lift.n == 0


def test_only_days_before_as_of_are_used():
    sales = [*usual_lunches(FESTIVAL_DAY), sold(FESTIVAL_DAY, LUNCH, {"1": 1, "2": 3})]
    lift = menu_share_lift(inputs(sales, events=[festival(FESTIVAL_DAY)]), "EVENT", "LOCAL_FESTIVAL", FESTIVAL_DAY)
    assert lift.n == 0  # 기준일 당일의 축제는 쓰지 않는다


def test_days_are_averaged_with_equal_weight():
    second = FESTIVAL_DAY + dt.timedelta(days=7)
    sales = [
        *usual_lunches(FESTIVAL_DAY),
        *[sold(day, LUNCH, {"1": 3, "2": 1}) for day in days(FESTIVAL_DAY + dt.timedelta(days=1), second - dt.timedelta(days=1))],
        sold(FESTIVAL_DAY, LUNCH, {"1": 1, "2": 3}),  # 첫 축제: 전 +50%p (4개)
        sold(second, LUNCH, {"2": 2}),  # 두 번째 축제: 전 +75%p (2개). 평소 구간에서 첫 축제 칸은 빠진다
    ]
    events = [festival(FESTIVAL_DAY), festival(second, event_id="event_002")]
    lift = menu_share_lift(inputs(sales, events=events), "EVENT", "LOCAL_FESTIVAL", AS_OF)
    assert lift.n == 2
    assert lift.lift_pp["2"] == pytest.approx(62.5)  # (50 + 75) / 2. 수량을 모두 합쳤다면 58.3


def test_other_game_kinds_are_not_counted():
    game_day = FESTIVAL_DAY
    baseball = Game(game_id="game_001", kind="BASEBALL", title="프로야구", start_at=at(game_day, 11))
    national = Game(game_id="game_002", kind="NATIONAL_TEAM", title="국가대표 축구", start_at=at(game_day + dt.timedelta(days=1), 11))
    sales = [
        *usual_lunches(game_day),
        sold(game_day, LUNCH, {"1": 1, "2": 3}),
        sold(game_day + dt.timedelta(days=1), LUNCH, {"1": 4}),
    ]
    lift = menu_share_lift(inputs(sales, games=[baseball, national]), "GAME", "BASEBALL", AS_OF)
    assert lift.n == 1
    assert lift.lift_pp["2"] == pytest.approx(50.0)


WINTER_START = dt.date(2026, 1, 5)


def winter_weather() -> list[WeatherDay]:
    """1/5~1/7 최고 5도(겨울 시작), 그 밖은 15도. 1/8 부터 사흘 10도 이상이라 겨울은 1/5~1/7"""
    cold = set(days(WINTER_START, WINTER_START + dt.timedelta(days=2)))
    return [WeatherDay(date=day, temp_max=5 if day in cold else 15, temp_min=0, rain_mm=0) for day in days(dt.date(2025, 10, 1), dt.date(2026, 1, 31))]


def test_season_compares_with_eight_weeks_before_the_season_started():
    winter_days = days(WINTER_START, WINTER_START + dt.timedelta(days=2))
    before = days(WINTER_START - dt.timedelta(days=56), WINTER_START - dt.timedelta(days=1))
    sales = [*usual_lunches(WINTER_START), *[sold(day, DINNER, {"1": 3, "2": 1}) for day in before]]  # 평소 점심·저녁 모두 75% : 25%
    for day in winter_days:
        sales.append(sold(day, LUNCH, {"1": 1, "2": 3}))  # 겨울 점심: 전 75%
    middle = winter_days[1]
    sales.append(sold(middle, DINNER, {"1": 1, "2": 3}))
    events = [festival(middle, 11, 15)]  # 겨울 둘째 날 점심 축제 칸은 뺀다 → 그날은 저녁만 본다
    sales.append(sold(middle, LUNCH, {"1": 40}))
    lift = menu_share_lift(inputs(sales, events=events, weather=winter_weather()), "SEASON", "WINTER", dt.date(2026, 3, 1))
    assert lift.n == 3
    # 그날 직전 8주를 평소로 썼다면 셋째 날 평소에 겨울 날이 섞여 50 보다 작게 나온다
    assert lift.lift_pp == {"1": pytest.approx(-50.0), "2": pytest.approx(50.0), "3": 0.0}


def test_season_needs_four_weeks_before_the_season_started():
    sales = [*usual_lunches(WINTER_START, weeks=3), *[sold(day, LUNCH, {"2": 1}) for day in days(WINTER_START, WINTER_START + dt.timedelta(days=2))]]
    lift = menu_share_lift(inputs(sales, weather=winter_weather()), "SEASON", "WINTER", dt.date(2026, 3, 1))
    assert lift.n == 0


def test_season_day_compares_only_the_dayparts_it_used():
    # 평소(겨울 전 8주): 점심 국수 3 · 전 1, 저녁 국수 1 · 전 1. 겨울 하루는 점심 축제 칸을 빼고 저녁만 본다
    usual = [*usual_lunches(WINTER_START), *[sold(day, DINNER, {"1": 1, "2": 1}) for day in days(WINTER_START - dt.timedelta(days=56), WINTER_START - dt.timedelta(days=1))]]
    sales = [*usual, sold(WINTER_START, LUNCH, {"1": 9}), sold(WINTER_START, DINNER, {"2": 2})]
    lift = menu_share_lift(inputs(sales, events=[festival(WINTER_START)], weather=winter_weather()), "SEASON", "WINTER", dt.date(2026, 3, 1))
    assert lift.n == 1
    assert lift.lift_pp["2"] == pytest.approx(50.0)  # 저녁끼리: 100% − 50%. 점심까지 섞으면 100% − 33.3%


def test_restarted_season_leaves_earlier_days_of_the_same_season_out_of_usual():
    # 겨울 1/5~1/7 → 따뜻한 1/8~1/10 → 다시 겨울 1/11~1/13. 두 번째 겨울의 평소(1/11 전 8주)에서 첫 겨울 날은 뺀다
    first = days(WINTER_START, WINTER_START + dt.timedelta(days=2))
    warm = days(WINTER_START + dt.timedelta(days=3), WINTER_START + dt.timedelta(days=5))
    second = days(WINTER_START + dt.timedelta(days=6), WINTER_START + dt.timedelta(days=8))
    cold = set(first) | set(second)
    weather = [WeatherDay(date=day, temp_max=5 if day in cold else 15, temp_min=0, rain_mm=0) for day in days(dt.date(2025, 10, 1), dt.date(2026, 1, 31))]
    sales = [
        *usual_lunches(WINTER_START),
        *[sold(day, LUNCH, {"1": 1, "2": 3}) for day in first + second],  # 겨울 점심: 전 75%
        *[sold(day, LUNCH, {"1": 3, "2": 1}) for day in warm],
    ]
    lift = menu_share_lift(inputs(sales, weather=weather), "SEASON", "WINTER", dt.date(2026, 3, 1))
    assert lift.n == 6
    assert lift.lift_pp["2"] == pytest.approx(50.0)  # 첫 겨울 날이 평소에 섞이면 두 번째 겨울의 변화가 50 보다 작다
