"""우리 매장 달력 (app/analysis/store_calendar/calendar_day.py).

달력 칸은 기준선에 태그의 효과를 더한 예상 매출과, 그 비율로 정한 신호다. now 의 날짜부터 35일을 만든다.
"""

import datetime as dt

import pytest

from app.analysis.input_shapes import AnalysisInputs, Order, StoreInfo, WeatherDay
from app.analysis.mock_csv_reader import MOCK_DIR, read_mock_csv
from app.analysis.store_calendar.calendar_day import build_calendar_days
from app.core.seoul_time import SEOUL
from app.planner.data_shapes import CalendarReason, Event, Game

STORE = StoreInfo(store_id="s1", name="테스트", lat=0, lng=0, open_time=dt.time(10), close_time=dt.time(22))
TODAY = dt.date(2026, 11, 16)  # 월요일
NOW = dt.datetime(2026, 11, 16, 22, 30, tzinfo=SEOUL)
SALES = {"MORNING": (10, 30, 10_000), "LUNCH": (12, 0, 500_000), "DINNER": (18, 0, 800_000)}  # 시간대별 하루 주문 하나


def at(day: dt.date, hour: int, minute: int = 0) -> dt.datetime:
    return dt.datetime(day.year, day.month, day.day, hour, minute, tzinfo=SEOUL)


def daily_orders(days: int = 56, sales: dict[tuple[dt.date, str], int] | None = None) -> list[Order]:
    """오늘까지 days 일 동안 시간대마다 주문 하나. 따로 정하지 않은 칸은 SALES 금액."""
    sales = sales or {}
    orders = []
    for n in range(days):
        day = TODAY - dt.timedelta(days=n)
        for daypart, (hour, minute, amount) in SALES.items():
            orders.append(
                Order(order_id=f"{day}-{daypart}", ordered_at=at(day, hour, minute), channel="HALL", total_amount=sales.get((day, daypart), amount))
            )
    return orders


def by_cell(rows):
    return {(r.date, r.daypart): r for r in rows}


def test_usual_days_are_normal_for_35_days_and_closed_days_have_no_rows():
    rows = build_calendar_days(AnalysisInputs(store=STORE, orders=daily_orders()), NOW)

    assert len(rows) == 35 * 3
    assert {r.date for r in rows} == {TODAY + dt.timedelta(days=n) for n in range(35)}
    lunch = by_cell(rows)[(TODAY + dt.timedelta(days=3), "LUNCH")]
    assert (lunch.signal, lunch.baseline_sales, lunch.expected_sales, lunch.ratio) == ("NORMAL", 500_000, 500_000, 1.0)
    assert (lunch.reasons, lunch.reason_text, lunch.computed_at) == ([], "평소와 비슷할 것 같아요", NOW)

    closed = STORE.model_copy(update={"closed_weekdays": ["TUE"]})
    rows = build_calendar_days(AnalysisInputs(store=closed, orders=daily_orders()), NOW)
    assert all(r.date.weekday() != 1 for r in rows)
    assert len(rows) == 30 * 3  # 35일 중 화요일 5번


def festival(event_id: str, day: dt.date, title: str = "지역 축제") -> Event:
    return Event(event_id=event_id, kind="LOCAL_FESTIVAL", title=title, start_at=at(day, 12), end_at=at(day, 13), distance_km=0.5)


LAST_MONDAY, THURSDAY = TODAY - dt.timedelta(days=7), TODAY + dt.timedelta(days=3)


def festival_thursday_lunch(past_festival_lunch: int, future_events: list[Event] | None = None):
    """지난 월요일 점심 축제(매출 past_festival_lunch, 평소 500,000원)와 이번 목요일 점심 축제. 목요일 점심 기준선은 333,333원."""
    thursdays = {(TODAY - dt.timedelta(days=n), "LUNCH"): 333_333 for n in range(4, 56, 7)}
    orders = daily_orders(sales={(LAST_MONDAY, "LUNCH"): past_festival_lunch, **thursdays})
    events = [festival("event_001", LAST_MONDAY), *(future_events or [festival("event_002", THURSDAY)])]
    return by_cell(build_calendar_days(AnalysisInputs(store=STORE, orders=orders, events=events), NOW))[(THURSDAY, "LUNCH")]


def test_a_tagged_event_raises_the_expected_sales():
    cell = festival_thursday_lunch(733_333)

    # 과거 효과: 733,333 / 500,000 − 1 = 0.4667 → 0.47. 예상: 333,333 × 1.47 = 489,999.51 → 내림 489,999
    assert cell.reasons == [CalendarReason(tag="EVENT", ref_id="event_002", effect=0.47)]
    assert (cell.baseline_sales, cell.expected_sales, cell.ratio, cell.signal) == (333_333, 489_999, 1.47, "HIGH")
    assert cell.reason_text == "지역 축제 영향으로 평소보다 47% 많을 것 같아요"


def test_small_effects_get_no_reason_season_always_does_and_effects_add_up():
    last_monday, two_mondays_ago = TODAY - dt.timedelta(days=7), TODAY - dt.timedelta(days=14)
    wednesday, sunday, next_monday = (TODAY + dt.timedelta(days=n) for n in (2, 6, 7))
    orders = daily_orders(sales={
        (last_monday, "LUNCH"): 750_000,  # 지역 축제 +50%
        (last_monday, "DINNER"): 840_000,  # 야구 +5% → 태그 없음
        (two_mondays_ago, "DINNER"): 640_000,  # 비 −20%
    })
    inputs = AnalysisInputs(
        store=STORE,
        orders=orders,
        events=[festival("event_001", last_monday), festival("event_002", next_monday)],
        games=[
            Game(game_id="game_001", kind="BASEBALL", title="야구 경기", start_at=at(last_monday, 18)),
            Game(game_id="game_002", kind="BASEBALL", title="야구 경기", start_at=at(wednesday, 18)),
        ],
        weather=[
            WeatherDay(date=two_mondays_ago, temp_max=15, temp_min=8, rain_mm=12),
            WeatherDay(date=wednesday, temp_max=15, temp_min=8, rain_mm=12),
            *(WeatherDay(date=TODAY + dt.timedelta(days=n), temp_max=5, temp_min=-2, rain_mm=0) for n in (5, 6, 7)),  # 토요일부터 겨울
        ],
    )

    cells = by_cell(build_calendar_days(inputs, NOW))

    rainy = cells[(wednesday, "DINNER")]  # 야구(+5%)는 이유가 없고 비(−20%)만 남는다
    assert rainy.reasons == [CalendarReason(tag="WEATHER", ref_id=f"weather:{wednesday}:RAIN", effect=-0.2)]
    assert (rainy.expected_sales, rainy.ratio, rainy.signal) == (640_000, 0.8, "LOW")
    assert rainy.reason_text == "비 영향으로 평소보다 20% 적을 것 같아요"
    assert cells[(wednesday, "LUNCH")].reasons == []  # 비 오는 점심은 과거 효과가 0이라 이유가 없다

    winter_only = cells[(sunday, "DINNER")]
    assert winter_only.reasons == [CalendarReason(tag="SEASON", ref_id="season_winter", effect=0.05)]
    assert (winter_only.ratio, winter_only.signal, winter_only.reason_text) == (1.05, "NORMAL", "겨울 영향으로 평소보다 5% 많을 것 같아요")

    both = cells[(next_monday, "LUNCH")]
    assert [r.tag for r in both.reasons] == ["EVENT", "SEASON"]
    assert (both.expected_sales, both.ratio, both.signal) == (775_000, 1.55, "HIGH")  # 500,000 × (1 + 0.50 + 0.05)
    assert both.reason_text == "지역 축제 · 겨울 영향으로 평소보다 55% 많을 것 같아요"


def test_a_cell_without_baseline_keeps_its_row_empty_and_normal():
    """기준선이 없으면(같은 요일 4주 미만) 효과 판정을 건너뛴다. 계절이나 행사가 있어도 이유를 붙이지 않는다."""
    thursday = TODAY + dt.timedelta(days=3)
    inputs = AnalysisInputs(
        store=STORE,
        orders=daily_orders(days=14),  # 2주뿐
        events=[festival("event_001", thursday)],
        weather=[WeatherDay(date=TODAY + dt.timedelta(days=n), temp_max=5, temp_min=-2, rain_mm=0) for n in range(5)],
    )

    cell = by_cell(build_calendar_days(inputs, NOW))[(thursday, "LUNCH")]

    assert (cell.baseline_sales, cell.expected_sales, cell.ratio) == (None, None, None)
    assert (cell.signal, cell.reasons, cell.reason_text) == ("NORMAL", [], "평소와 비슷할 것 같아요")


def test_signal_is_judged_on_the_rounded_ratio():
    cell = festival_thursday_lunch(575_000)  # 효과 정확히 +15%

    # 333,333 × 1.15 = 383,332.95 → 내림 383,332. 383,332 / 333,333 = 1.149997 → 반올림 1.15 → HIGH
    assert (cell.expected_sales, cell.ratio, cell.signal) == (383_332, 1.15, "HIGH")



def test_a_zero_baseline_keeps_zero_but_has_no_ratio():
    """평소 0원인 칸은 기준선 0을 그대로 두고, 비율을 구할 수 없어 예상·비율은 비운다."""
    no_mornings = {(TODAY - dt.timedelta(days=n), "MORNING"): 0 for n in range(56)}
    cell = by_cell(build_calendar_days(AnalysisInputs(store=STORE, orders=daily_orders(sales=no_mornings)), NOW))[(TODAY, "MORNING")]

    assert (cell.baseline_sales, cell.expected_sales, cell.ratio) == (0, None, None)
    assert (cell.signal, cell.reasons, cell.reason_text) == ("NORMAL", [], "평소와 비슷할 것 같아요")


def test_expected_sales_never_go_below_zero():
    """한 과거 칸에 비와 행사가 겹쳐 두 효과가 모두 −80% 이면, 둘이 같이 오는 칸은 −160% 지만 0원에서 멈춘다."""
    last_monday, wednesday = TODAY - dt.timedelta(days=7), TODAY + dt.timedelta(days=2)
    dinner_event = lambda event_id, day: Event(  # noqa: E731
        event_id=event_id, kind="MARATHON", title="마라톤", start_at=at(day, 18), end_at=at(day, 19), distance_km=0.5
    )
    inputs = AnalysisInputs(
        store=STORE,
        orders=daily_orders(sales={(last_monday, "DINNER"): 160_000}),
        events=[dinner_event("event_001", last_monday), dinner_event("event_002", wednesday)],
        weather=[WeatherDay(date=day, temp_max=15, temp_min=8, rain_mm=12) for day in (last_monday, wednesday)],
    )

    cell = by_cell(build_calendar_days(inputs, NOW))[(wednesday, "DINNER")]

    assert [r.effect for r in cell.reasons] == [-0.8, -0.8]
    assert (cell.expected_sales, cell.ratio, cell.signal) == (0, 0.0, "LOW")


def test_two_reasons_of_the_same_group_in_one_cell_count_once():
    """같은 칸에 같은 종류 축제가 둘이면 ref_id 가 앞선 하나만 이유로 남고 효과도 한 번만 더한다."""
    cell = festival_thursday_lunch(666_666, [festival("event_003", THURSDAY, "둘째 축제"), festival("event_002", THURSDAY)])

    # 과거 효과 666,666 / 500,000 − 1 = 0.33. 두 번 더하면 333,333 × 1.66 이 된다
    assert cell.reasons == [CalendarReason(tag="EVENT", ref_id="event_002", effect=0.33)]
    assert (cell.expected_sales, cell.reason_text) == (443_332, "지역 축제 영향으로 평소보다 33% 많을 것 같아요")


def test_heat_cold_and_summer_read_by_name():
    two_mondays_ago, wednesday = TODAY - dt.timedelta(days=14), TODAY + dt.timedelta(days=2)
    orders = daily_orders(sales={(LAST_MONDAY, "DINNER"): 600_000, (two_mondays_ago, "LUNCH"): 600_000})
    inputs = AnalysisInputs(
        store=STORE,
        orders=orders,
        weather=[
            WeatherDay(date=LAST_MONDAY, temp_max=35, temp_min=25, rain_mm=0),  # 폭염 저녁 −25%
            WeatherDay(date=two_mondays_ago, temp_max=-5, temp_min=-15, rain_mm=0),  # 한파 점심 +20%
            WeatherDay(date=wednesday, temp_max=34, temp_min=24, rain_mm=0),
            WeatherDay(date=THURSDAY, temp_max=-4, temp_min=-13, rain_mm=0),
            *(WeatherDay(date=TODAY + dt.timedelta(days=n), temp_max=28, temp_min=20, rain_mm=0) for n in (8, 9, 10)),  # 여름
        ],
    )

    cells = by_cell(build_calendar_days(inputs, NOW))

    assert cells[(wednesday, "DINNER")].reason_text == "폭염 영향으로 평소보다 25% 적을 것 같아요"
    assert cells[(THURSDAY, "LUNCH")].reason_text == "한파 영향으로 평소보다 20% 많을 것 같아요"
    assert cells[(TODAY + dt.timedelta(days=8), "LUNCH")].reason_text == "여름 영향으로 평소보다 5% 많을 것 같아요"

# ── 목업 데이터: 우리 매장 달력 완료 기준 ──
# 목업 CSV 에는 데모 주(11/18~22) 경기·행사가 없어서, 계획 엔진 샘플과 같은 id·시각으로 덧붙인다.
# 효과값은 고정하지 않고 태그와 신호를 본다(원본 CSV 손 계산: 국가대표 저녁 +35%, 지역 축제 점심 +18%·저녁 +49%).


def nov(day: int, hour: int = 0, minute: int = 0) -> dt.datetime:
    return dt.datetime(2026, 11, day, hour, minute, tzinfo=SEOUL)


@pytest.mark.skipif(not (MOCK_DIR / "orders.csv").exists(), reason="목업 CSV 가 없다")
def test_mock_demo_week_calendar():
    inputs = read_mock_csv()
    inputs = inputs.model_copy(update={
        "games": [
            *inputs.games,
            Game(game_id="game_028", kind="BASEBALL", title="프로야구 경기", start_at=nov(18, 18, 30)),
            Game(game_id="game_031", kind="NATIONAL_TEAM", title="국가대표 축구 경기", start_at=nov(19, 20)),
        ],
        "events": [
            *inputs.events,
            Event(event_id="event_012", kind="LOCAL_FESTIVAL", title="지역 축제", start_at=nov(21, 11), end_at=nov(22, 18), distance_km=0.8),
        ],
    })

    rows = build_calendar_days(inputs, nov(17, 22, 30))
    cells = {(r.date.day if r.date.month == 11 else None, r.daypart): r for r in rows}

    def tags(day: int, daypart: str) -> list[str]:
        return [reason.tag for reason in cells[(day, daypart)].reasons]

    assert len(rows) == 35 * 3 and rows[0].date == dt.date(2026, 11, 17)
    assert (tags(18, "DINNER"), cells[(18, "DINNER")].signal) == ([], "NORMAL")  # 야구는 효과가 작아 태그 없음
    assert (tags(19, "DINNER"), cells[(19, "DINNER")].signal) == (["GAME"], "HIGH")
    assert cells[(19, "DINNER")].reasons[0].ref_id == "game_031"
    for daypart in ("LUNCH", "DINNER"):
        assert (tags(21, daypart), cells[(21, daypart)].signal) == (["EVENT"], "HIGH")
    assert tags(21, "MORNING") == []  # 행사는 11시에 시작한다
    for daypart in ("MORNING", "LUNCH", "DINNER"):
        assert (tags(22, daypart), cells[(22, daypart)].signal) == (["EVENT", "SEASON"], "HIGH")
    assert all("SEASON" not in tags(day, p) for day in range(17, 22) for p in ("MORNING", "LUNCH", "DINNER"))
    assert all(any(reason.ref_id == "season_winter" for reason in r.reasons) for r in rows if r.date >= dt.date(2026, 11, 22))
