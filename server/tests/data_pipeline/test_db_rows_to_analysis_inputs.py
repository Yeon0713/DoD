"""DB 행 → 태성 분석 입력 번역 테스트. server/ 폴더에서 `python -m pytest` 로 실행한다.

지호의 개발 DB 파일(db/data/*.db)을 읽기만 한다.
"""

import datetime as dt

from app.core.seoul_time import SEOUL
from app.data_pipeline import read_store_db
from app.data_pipeline.db_rows_to_analysis_inputs import (
    build_analysis_inputs,
    distance_km,
    review_id_of,
    review_platform,
    sales_dayparts,
)

NOW = dt.datetime(2026, 11, 12, 15, 0, tzinfo=SEOUL)


def ranges(open_hhmm: str, close_hhmm: str) -> list[tuple[str, str, str]]:
    result = sales_dayparts(dt.time.fromisoformat(open_hhmm), dt.time.fromisoformat(close_hhmm))
    return [(r.daypart, r.start.strftime("%H:%M"), r.end.strftime("%H:%M")) for r in result]


def test_dayparts_split_into_lunch_dinner_night():
    assert ranges("10:00", "22:00") == [("LUNCH", "10:00", "15:00"), ("DINNER", "15:00", "20:00"), ("NIGHT", "20:00", "22:00")]


def test_dayparts_of_overnight_store_skip_lunch_and_cross_midnight():
    assert ranges("17:00", "03:00") == [("DINNER", "17:00", "20:00"), ("NIGHT", "20:00", "03:00")]


def test_review_platform_rule():
    assert review_platform("delivery") == "BAEMIN"
    assert review_platform("hall") == "NAVER"
    assert review_platform(None) == "NAVER"


def test_id_format():
    assert review_id_of(7) == "rv_007"


def test_distance_is_measured_per_store():
    event = read_store_db.read_events()[2]  # 강원대 대동제
    s001, s003 = read_store_db.read_store("s001"), read_store_db.read_store("s003")
    near = distance_km(s001["lat"], s001["lng"], event["lat"], event["lng"])
    far = distance_km(s003["lat"], s003["lng"], event["lat"], event["lng"])
    assert near < far


def test_inputs_only_contain_data_until_now():
    inputs = build_analysis_inputs("s001", NOW)
    assert inputs.orders and inputs.reviews and inputs.shifts
    assert all(order.ordered_at <= NOW for order in inputs.orders)
    assert all(review.written_at <= NOW for review in inputs.reviews)
    assert all(shift.starts_at <= NOW for shift in inputs.shifts)
    assert {order.channel for order in inputs.orders} == {"HALL", "DELIVERY"}
    assert all(review.label is None for review in inputs.reviews)  # 분류는 태성 분석이 붙인다
    assert inputs.events[0].event_id == "event_001"


def test_review_order_ids_match_order_ids():
    inputs = build_analysis_inputs("s001", NOW)
    order_ids = {order.order_id for order in inputs.orders}
    linked = [review for review in inputs.reviews if review.order_id]
    assert linked and all(review.order_id in order_ids for review in linked)
    assert all(review.platform == "BAEMIN" for review in linked)
