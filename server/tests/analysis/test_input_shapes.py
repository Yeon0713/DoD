"""분석 입력 모양 (app/analysis/input_shapes.py): 시간대 없는(naive) 시각을 입력 단계에서 막는다.

naive 시각은 컴퓨터의 시스템 시간대로 해석돼 서버에 따라 칸이 9시간 밀린다. 서울 시각으로 바꿔 주지 않고 거절한다.
"""

import datetime as dt

import pytest
from pydantic import ValidationError

from app.analysis.input_shapes import AnalysisInputs, Order, Shift, StoreInfo
from app.analysis.pattern.sales_daily import build_sales_daily
from app.core.seoul_time import SEOUL
from app.planner.data_shapes import Event, Game, Review

STORE = StoreInfo(store_id="s1", name="테스트", lat=0, lng=0, open_time=dt.time(10), close_time=dt.time(22))
NAIVE = dt.datetime(2026, 11, 17, 10, 30)
AWARE = NAIVE.replace(tzinfo=SEOUL)


def test_naive_order_and_shift_times_are_rejected():
    with pytest.raises(ValidationError):
        Order(order_id="1", ordered_at=NAIVE, channel="HALL", total_amount=9000)
    with pytest.raises(ValidationError):
        Shift(shift_id="1", staff_key="staff_001", starts_at=AWARE, ends_at=NAIVE, hourly_wage=10000)


@pytest.mark.parametrize(
    "changes",
    [
        {"events": [Event(event_id="event_001", kind="LOCAL_EVENT", title="축제", start_at=NAIVE, end_at=AWARE, distance_km=1.0)]},
        {"games": [Game(game_id="game_001", kind="BASEBALL", title="야구", start_at=NAIVE)]},
        {"reviews": [Review(review_id="rv_001", platform="NAVER", written_at=NAIVE, rating=5, text="맛있어요")]},
    ],
)
def test_naive_times_in_shared_shapes_are_rejected(changes):
    with pytest.raises(ValidationError):
        AnalysisInputs(store=STORE, **changes)


def test_aware_times_in_other_zones_are_accepted():
    utc = AWARE.astimezone(dt.timezone.utc)
    order = Order(order_id="1", ordered_at=utc, channel="HALL", total_amount=9000)
    assert order.ordered_at == AWARE


def test_naive_now_is_rejected():
    with pytest.raises(ValueError):
        build_sales_daily(AnalysisInputs(store=STORE), NAIVE)
