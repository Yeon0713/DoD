"""손님 주문 주기 (app/analysis/customer_cycle/order_cycle.py)."""

import datetime as dt

import pytest

from app.analysis.customer_cycle.order_cycle import build_customer_cycles
from app.analysis.input_shapes import AnalysisInputs, Order, StoreInfo
from app.analysis.mock_csv_reader import MOCK_DIR, read_mock_csv
from app.analysis.result_shapes import load_fixture
from app.core.seoul_time import SEOUL

STORE = StoreInfo(store_id="s1", name="테스트", lat=0, lng=0, open_time=dt.time(10), close_time=dt.time(22))
NOW = dt.datetime(2026, 11, 15, 22, 30, tzinfo=SEOUL)


def at(text: str) -> dt.datetime:
    return dt.datetime.fromisoformat(text).replace(tzinfo=SEOUL)


def orders_of(customer_key: str, *times: str) -> list[Order]:
    return [
        Order(order_id=f"{customer_key}_{i}", ordered_at=at(t), channel="DELIVERY", customer_key=customer_key, total_amount=10000)
        for i, t in enumerate(times)
    ]


def cycles(orders: list[Order], now: dt.datetime = NOW) -> dict:
    return {row.customer_key: row for row in build_customer_cycles(AnalysisInputs(store=STORE, orders=orders), now)}


# 데모 손님: 매주 수요일 저녁 / 한 달에 한 번 저녁
C_W01 = orders_of("c_w01", "2026-10-21 18:10", "2026-10-28 18:20", "2026-11-04 18:30", "2026-11-11 18:20")
C_M01 = orders_of("c_m01", "2026-07-23 19:00", "2026-08-21 19:00", "2026-09-25 19:00", "2026-10-23 19:00")


def test_weekly_customer_matches_fixture():
    expected = {row.customer_key: row for row in load_fixture("customer_cycle")}["c_w01"]
    assert cycles(C_W01)["c_w01"] == expected


def test_monthly_customer_matches_fixture():
    expected = {row.customer_key: row for row in load_fixture("customer_cycle")}["c_m01"]
    assert cycles(C_M01)["c_m01"] == expected


def test_fewer_than_four_visits_is_none():
    row = cycles(orders_of("c", "2026-10-28 18:00", "2026-11-04 18:00", "2026-11-11 18:00"))["c"]
    assert (row.cycle, row.next_expected_at, row.expected_daypart, row.intervals_days) == ("NONE", None, None, [7, 7])


def test_orders_on_same_day_count_as_one_visit():
    """11/10 에 두 번 주문해도 방문은 한 번이라, 화요일 방문이 3번이 되지 않는다."""
    row = cycles(orders_of("c", "2026-10-27 18:00", "2026-11-05 18:00", "2026-11-10 18:00", "2026-11-10 19:00"))["c"]
    assert row.cycle == "NONE" and row.intervals_days == [9, 5]


def test_same_weekday_but_different_daypart_is_not_weekly():
    row = cycles(orders_of("c", "2026-10-21 12:00", "2026-10-28 18:00", "2026-11-04 12:00", "2026-11-11 18:00"))["c"]
    assert row.cycle == "NONE"


def test_weekly_is_checked_before_monthly():
    row = cycles(orders_of("c", "2026-10-14 18:00", "2026-10-21 18:00", "2026-10-28 18:00", "2026-11-11 18:00"))["c"]
    assert row.cycle == "WEEKLY" and row.intervals_days == [7, 7, 14]


def test_stale_customers_become_none():
    weekly_long_ago = orders_of("w", "2026-09-30 18:00", "2026-10-07 18:00", "2026-10-14 18:00", "2026-10-21 18:00")
    monthly_long_ago = orders_of("m", "2026-05-01 19:00", "2026-06-01 19:00", "2026-07-01 19:00", "2026-08-01 19:00")
    result = cycles(weekly_long_ago + monthly_long_ago)
    assert result["w"].cycle == "NONE" and result["m"].cycle == "NONE"


def test_orders_after_now_and_without_customer_key_are_ignored():
    future = orders_of("c_w01", "2026-11-18 18:20")
    no_key = [Order(order_id="x", ordered_at=at("2026-11-11 12:00"), channel="HALL", total_amount=9000)]
    result = cycles(C_W01 + future + no_key)
    assert set(result) == {"c_w01"} and result["c_w01"].next_expected_at == at("2026-11-18 18:20")


def test_morning_visits_give_morning_daypart():
    row = cycles(orders_of("c", "2026-10-21 10:20", "2026-10-28 10:30", "2026-11-04 10:40", "2026-11-11 10:30"))["c"]
    assert (row.cycle, row.expected_daypart) == ("WEEKLY", "MORNING")


@pytest.mark.skipif(not (MOCK_DIR / "orders.csv").exists(), reason="목업 CSV 가 없다")
def test_mock_orders_give_one_row_per_customer():
    inputs = read_mock_csv()
    rows = build_customer_cycles(inputs, NOW)
    keys = {o.customer_key for o in inputs.orders if o.customer_key and o.ordered_at <= NOW}
    assert {row.customer_key for row in rows} == keys
    assert all(row.computed_at == NOW for row in rows)
    for row in rows:
        assert (row.next_expected_at is None) == (row.cycle == "NONE")
