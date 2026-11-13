"""목업 CSV 읽기 (app/analysis/mock_csv_reader.py)."""

import csv
from pathlib import Path

import pytest

from app.analysis.mock_csv_reader import game_kind, read_mock_csv

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "mock_v1"  # 손계산 기대값을 계산한 목업 v1 (고정)


@pytest.fixture(scope="module")
def inputs():
    return read_mock_csv(FIXTURE_DIR)


def csv_count(table: str) -> int:
    with (FIXTURE_DIR / f"{table}.csv").open(encoding="utf-8") as f:
        return sum(1 for _ in csv.DictReader(f))


def test_every_row_is_read(inputs):
    assert len(inputs.orders) == csv_count("orders")
    assert len(inputs.order_items) == csv_count("order_items")
    assert len(inputs.menus) == csv_count("menu")
    assert len(inputs.shifts) == csv_count("shifts")
    assert len(inputs.events) == csv_count("events")
    assert len(inputs.games) == csv_count("games")
    assert len(inputs.weather) == csv_count("weather_daily")
    assert len(inputs.reviews) == csv_count("reviews")


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
    assert game_kind("esports", "pro") == "ESPORTS"


def copy_mock_with(tmp_path, table: str, column: str, row_index: int, value: str):
    """목업 CSV 를 tmp_path 로 복사하고 한 칸만 바꾼다."""
    for src in FIXTURE_DIR.glob("*.csv"):
        (tmp_path / src.name).write_bytes(src.read_bytes())
    path = tmp_path / f"{table}.csv"
    with path.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fields, rows = reader.fieldnames, list(reader)
    rows[row_index][column] = value
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return tmp_path, rows[row_index]


def test_unknown_event_kind_is_kept_as_local_event(tmp_path, caplog):
    """행사는 종류와 관계없이 특별한 칸이라 버리지 않는다."""
    directory, changed = copy_mock_with(tmp_path, "events", "kind", 0, "concert")
    inputs = read_mock_csv(directory)
    assert len(inputs.events) == csv_count("events")
    assert {event.title: event.kind for event in inputs.events}[changed["name"]] == "LOCAL_EVENT"
    assert "concert" in caplog.text


def test_unknown_sport_is_skipped_with_warning(tmp_path, caplog):
    directory, _ = copy_mock_with(tmp_path, "games", "sport", 1, "curling")
    inputs = read_mock_csv(directory)
    assert len(inputs.games) == csv_count("games") - 1
    assert len(inputs.orders) == csv_count("orders")  # 나머지 입력은 그대로 읽는다
    assert "curling" in caplog.text


def test_store_uses_default_dayparts_and_times_are_seoul(inputs):
    assert inputs.store.dayparts is None
    assert str(inputs.store.open_time) == "10:00:00" and str(inputs.store.close_time) == "22:00:00"
    assert all(order.ordered_at.utcoffset().total_seconds() == 9 * 3600 for order in inputs.orders[:50])


def test_menu_cost_is_missing_and_wages_are_joined(inputs):
    assert all(menu.unit_cost is None for menu in inputs.menus)
    assert all(shift.hourly_wage > 0 for shift in inputs.shifts)


def test_reviews_are_unlabeled_with_prefixed_ids(inputs):
    review = inputs.reviews[0]
    assert review.review_id == "rv_001" and review.label is None and review.text
    order_ids = {order.order_id for order in inputs.orders}
    for review in inputs.reviews:
        assert review.platform == ("BAEMIN" if review.order_id else "NAVER")
        assert review.order_id is None or review.order_id in order_ids
