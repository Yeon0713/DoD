"""시간대 판정과 하루 × 시간대 매출 (app/analysis/pattern/daypart_time.py, sales_daily.py)."""

import datetime as dt
from pathlib import Path

import pytest

from app.analysis.input_shapes import AnalysisInputs, DaypartRange, Menu, Order, OrderItem, Shift, StoreInfo
from app.analysis.mock_csv_reader import read_mock_csv
from app.analysis.pattern.daypart_time import daypart_at, dayparts_of
from app.analysis.pattern.sales_daily import build_sales_daily
from app.core.seoul_time import SEOUL

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "mock_v1"  # 손계산 기대값을 계산한 목업 v1 (고정)
STORE = StoreInfo(store_id="s1", name="테스트", lat=0, lng=0, open_time=dt.time(10), close_time=dt.time(22))
DAY = dt.date(2026, 11, 2)  # 월요일


def at(hour: int, minute: int = 0, day: dt.date = DAY) -> dt.datetime:
    return dt.datetime(day.year, day.month, day.day, hour, minute, tzinfo=SEOUL)


def order(order_id: str, t: dt.datetime, amount: int) -> Order:
    return Order(order_id=order_id, ordered_at=t, channel="HALL", total_amount=amount)


def by_daypart(result, day: dt.date = DAY):
    return {row.daypart: row for row in result.rows if row.date == day}


# ── 시간대 판정 ──


def test_default_dayparts_follow_open_and_close():
    ranges = dayparts_of(STORE)
    assert [(r.daypart, str(r.start), str(r.end)) for r in ranges] == [
        ("MORNING", "10:00:00", "11:00:00"),
        ("LUNCH", "11:00:00", "17:00:00"),
        ("DINNER", "17:00:00", "22:00:00"),
    ]


@pytest.mark.parametrize("hour, minute, expected", [
    (9, 59, None), (10, 0, "MORNING"), (10, 59, "MORNING"), (11, 0, "LUNCH"),
    (16, 59, "LUNCH"), (17, 0, "DINNER"), (21, 59, "DINNER"), (22, 0, None),
])
def test_daypart_boundaries(hour, minute, expected):
    assert daypart_at(at(hour, minute), dayparts_of(STORE)) == expected


def test_owner_dayparts_are_used_when_set():
    store = STORE.model_copy(update={"dayparts": [
        DaypartRange(daypart="MORNING", start=dt.time(10), end=dt.time(11, 30)),
        DaypartRange(daypart="LUNCH", start=dt.time(11, 30), end=dt.time(16)),
        DaypartRange(daypart="DINNER", start=dt.time(16), end=dt.time(22)),
    ]})
    assert daypart_at(at(11, 15), dayparts_of(store)) == "MORNING"
    assert daypart_at(at(16, 30), dayparts_of(store)) == "DINNER"


# ── 하루 × 시간대 매출 ──


def sample_inputs(**changes) -> AnalysisInputs:
    data = dict(
        store=STORE,
        orders=[order("1", at(10, 30), 9000), order("2", at(12), 15000), order("3", at(18), 20000)],
        order_items=[
            OrderItem(order_id="1", menu_id="m1", quantity=1, unit_price=9000),
            OrderItem(order_id="2", menu_id="m1", quantity=1, unit_price=9000),
            OrderItem(order_id="2", menu_id="m2", quantity=2, unit_price=3000),
            OrderItem(order_id="3", menu_id="m1", quantity=2, unit_price=10000),
        ],
        menus=[Menu(menu_id="m1", name="국수", category="MAIN", price=9000), Menu(menu_id="m2", name="김밥", category="SIDE", price=3000)],
        shifts=[Shift(shift_id="1", staff_key="staff_001", starts_at=at(10, 30), ends_at=at(14), hourly_wage=10000)],
    )
    data.update(changes)
    return AnalysisInputs(**data)


END_OF_DAY = at(23)


def test_sales_and_qty_per_daypart():
    rows = by_daypart(build_sales_daily(sample_inputs(), END_OF_DAY))
    assert (rows["MORNING"].sales_amount, rows["MORNING"].qty) == (9000, 1)
    assert (rows["LUNCH"].sales_amount, rows["LUNCH"].qty) == (15000, 3)
    assert (rows["DINNER"].sales_amount, rows["DINNER"].qty) == (20000, 2)


def test_labor_cost_is_split_by_overlap():
    """10:30~14:00 근무, 시급 10,000원 → 아침 30분 5,000원, 점심 3시간 30,000원, 저녁 0원."""
    rows = by_daypart(build_sales_daily(sample_inputs(), END_OF_DAY))
    assert [rows[d].labor_cost for d in ("MORNING", "LUNCH", "DINNER")] == [5000, 30000, 0]


def test_missing_menu_cost_leaves_food_cost_empty_and_profit_uses_known_items():
    rows = by_daypart(build_sales_daily(sample_inputs(), END_OF_DAY))
    assert rows["LUNCH"].food_cost is None
    assert rows["LUNCH"].profit == 15000 - 30000
    assert rows["LUNCH"].platform_fee is None and rows["LUNCH"].delivery_fee is None and rows["LUNCH"].payment_fee is None


def test_known_menu_cost_fills_food_cost():
    menus = [
        Menu(menu_id="m1", name="국수", category="MAIN", price=9000, unit_cost=3000),
        Menu(menu_id="m2", name="김밥", category="SIDE", price=3000, unit_cost=1000),
    ]
    rows = by_daypart(build_sales_daily(sample_inputs(menus=menus), END_OF_DAY))
    assert rows["LUNCH"].food_cost == 3000 + 2 * 1000
    assert rows["LUNCH"].profit == 15000 - 5000 - 30000


def test_no_shifts_leaves_labor_cost_empty():
    rows = by_daypart(build_sales_daily(sample_inputs(shifts=[]), END_OF_DAY))
    assert all(row.labor_cost is None for row in rows.values())
    assert rows["DINNER"].profit == 20000


def test_orders_after_now_and_unfinished_days_are_left_out():
    before_close = at(21)
    assert build_sales_daily(sample_inputs(), before_close).rows == []  # 그 날 마감 전
    next_day_orders = [*sample_inputs().orders, order("4", at(12, day=DAY + dt.timedelta(1)), 7000)]
    result = build_sales_daily(sample_inputs(orders=next_day_orders), END_OF_DAY)
    assert {row.date for row in result.rows} == {DAY}


def test_outside_orders_are_counted_not_added():
    orders = [*sample_inputs().orders, order("9", at(9, 30), 5000), order("10", at(22, 10), 5000)]
    result = build_sales_daily(sample_inputs(orders=orders), END_OF_DAY)
    assert result.outside_order_count == 2
    assert sum(row.sales_amount for row in result.rows) == 9000 + 15000 + 20000


def test_closed_weekday_has_no_rows_and_empty_day_has_zero_rows():
    store = STORE.model_copy(update={"closed_weekdays": ["TUE"]})
    thursday = DAY + dt.timedelta(3)
    orders = [*sample_inputs().orders, order("4", at(12, day=thursday), 7000)]
    result = build_sales_daily(sample_inputs(store=store, orders=orders), at(23, day=thursday))
    assert {row.date for row in result.rows} == {DAY, DAY + dt.timedelta(2), thursday}  # 화요일 휴무
    assert all(row.sales_amount == 0 for row in result.rows if row.date == DAY + dt.timedelta(2))  # 주문 없는 수요일


def test_no_rows_after_the_last_order_day():
    """주문 데이터가 끝난 뒤의 날은 0원 칸을 만들지 않는다. 데이터가 안 들어온 날과 손님이 없던 날을 구별할 수 없다."""
    result = build_sales_daily(sample_inputs(), at(23, day=DAY + dt.timedelta(5)))
    assert {row.date for row in result.rows} == {DAY}


def test_mock_sales_daily_covers_all_orders_until_now():
    inputs = read_mock_csv(FIXTURE_DIR)
    now = dt.datetime(2026, 11, 15, 22, 30, tzinfo=SEOUL)
    result = build_sales_daily(inputs, now)
    days = {row.date for row in result.rows}
    assert len(result.rows) == len(days) * 3
    assert result.outside_order_count == 0
    assert sum(row.sales_amount for row in result.rows) == sum(o.total_amount for o in inputs.orders if o.ordered_at <= now)
    assert all(row.food_cost is None and row.labor_cost is not None for row in result.rows)


# ── 자정 넘어 영업하는 매장 (17:00 ~ 다음 날 03:00) ──

PUB = StoreInfo(store_id="s2", name="술집", lat=0, lng=0, open_time=dt.time(17), close_time=dt.time(3))


def test_store_open_and_close_cannot_be_same():
    with pytest.raises(ValueError):
        StoreInfo(store_id="s", name="x", lat=0, lng=0, open_time=dt.time(9), close_time=dt.time(9))


def test_overnight_store_has_one_dinner_daypart_past_midnight():
    assert PUB.overnight and not STORE.overnight
    assert [(r.daypart, str(r.start), str(r.end)) for r in dayparts_of(PUB)] == [("DINNER", "17:00:00", "03:00:00")]


def test_late_opening_store_has_no_morning():
    store = STORE.model_copy(update={"open_time": dt.time(12)})
    assert [r.daypart for r in dayparts_of(store)] == ["LUNCH", "DINNER"]


@pytest.mark.parametrize("hour, minute, expected", [
    (16, 59, None), (17, 0, "DINNER"), (23, 59, "DINNER"), (0, 0, "DINNER"), (2, 59, "DINNER"), (3, 0, None),
])
def test_overnight_daypart_boundaries(hour, minute, expected):
    assert daypart_at(at(hour, minute), dayparts_of(PUB)) == expected


def test_overnight_orders_after_midnight_belong_to_previous_business_day():
    next_day = DAY + dt.timedelta(days=1)
    orders = [
        order("o1", at(20), 10000),
        order("o2", at(1, 30, next_day), 20000),  # DAY 영업일의 새벽
        order("o3", at(18, 0, next_day), 5000),
    ]
    shift = Shift(shift_id="sh1", staff_key="staff_001", hourly_wage=10000,
                  starts_at=at(21, 30), ends_at=at(3, 30, next_day))
    now = at(3, 0, DAY + dt.timedelta(days=2))  # next_day 영업일 마감 시각
    result = build_sales_daily(AnalysisInputs(store=PUB, orders=orders, shifts=[shift]), now)

    assert result.outside_order_count == 0
    assert [(row.date, row.daypart, row.sales_amount) for row in result.rows] == [
        (DAY, "DINNER", 30000),
        (next_day, "DINNER", 5000),
    ]
    assert by_daypart(result)["DINNER"].labor_cost == 55000  # 21:30 ~ 다음 날 03:00, 5.5시간


def test_overnight_day_is_unfinished_until_closing_next_morning():
    orders = [order("o1", at(20), 10000), order("o2", at(1, 30, DAY + dt.timedelta(days=1)), 20000)]
    result = build_sales_daily(AnalysisInputs(store=PUB, orders=orders), at(2, 59, DAY + dt.timedelta(days=1)))
    assert result.rows == []
