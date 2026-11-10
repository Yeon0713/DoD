"""목업 CSV 읽기 (app/analysis/mock_csv_reader.py)."""

import csv

import pytest

from app.analysis.mock_csv_reader import MOCK_DIR, game_kind, read_mock_csv

pytestmark = pytest.mark.skipif(not (MOCK_DIR / "orders.csv").exists(), reason="목업 CSV 가 없다")


@pytest.fixture(scope="module")
def inputs():
    return read_mock_csv()


def csv_count(table: str) -> int:
    with (MOCK_DIR / f"{table}.csv").open(encoding="utf-8") as f:
        return sum(1 for _ in csv.DictReader(f))


def test_every_row_is_read(inputs):
    assert len(inputs.orders) == csv_count("orders")
    assert len(inputs.order_items) == csv_count("order_items")
    assert len(inputs.menus) == csv_count("menu")
    assert len(inputs.shifts) == csv_count("shifts")
    assert len(inputs.events) == csv_count("events")
    assert len(inputs.games) == csv_count("games")
    assert len(inputs.weather) == csv_count("weather_daily")


def test_codes_are_uppercase(inputs):
    assert {order.channel for order in inputs.orders} <= {"HALL", "DELIVERY"}
    assert {menu.category for menu in inputs.menus} == {"MAIN", "SIDE", "DRINK"}


def test_ids_are_strings_with_prefix(inputs):
    assert inputs.events[0].event_id == "event_001"
    assert inputs.games[0].game_id == "game_001"
    assert all(shift.staff_key.startswith("staff_") for shift in inputs.shifts)


def test_event_kinds_follow_contract(inputs):
    kinds = {event.title: event.kind for event in inputs.events}
    assert kinds["강원대 대동제"] == "UNIV_FESTIVAL"
    assert kinds["효자동 연말 플리마켓"] == "LOCAL_EVENT"


def test_game_kinds():
    assert game_kind("soccer", "national") == "NATIONAL_TEAM"
    assert game_kind("baseball", "national") == "NATIONAL_TEAM"
    assert game_kind("baseball", "pro") == "BASEBALL"
    assert game_kind("soccer", "pro") == "FOOTBALL"


def test_store_uses_default_dayparts_and_times_are_seoul(inputs):
    assert inputs.store.dayparts is None
    assert str(inputs.store.open_time) == "10:00:00" and str(inputs.store.close_time) == "22:00:00"
    assert all(order.ordered_at.utcoffset().total_seconds() == 9 * 3600 for order in inputs.orders[:50])


def test_menu_cost_is_missing_and_wages_are_joined(inputs):
    assert all(menu.unit_cost is None for menu in inputs.menus)
    assert all(shift.hourly_wage > 0 for shift in inputs.shifts)
