"""손님 주문 주기와 위험 신호를 계획 엔진에 넣었을 때 데모 주간 알림이 그대로 나오는지 본다.

계획 엔진 테스트 입력(tests/planner/sample_inputs/)의 customer_cycles, risk_signals 만 분석 결과로 바꾼다.
계획 엔진은 아직 MORNING 을 받지 못하므로 데모 손님은 저녁 손님만 쓴다.
"""

import datetime as dt
import json
from pathlib import Path

import pytest

from app.analysis.customer_cycle.order_cycle import build_customer_cycles
from app.analysis.input_shapes import AnalysisInputs, Order, StoreInfo
from app.analysis.result_shapes import RiskSignalRow, load_fixture
from app.analysis.review.risk_signals import update_risk_signals
from app.core.seoul_time import SEOUL
from app.planner.data_shapes import PlanInputs, Review
from app.planner.make_plan import make_plan

PLANNER_INPUTS = Path(__file__).parents[1] / "planner" / "sample_inputs" / "demo_week_inputs.example.json"
RAW = json.loads(PLANNER_INPUTS.read_text(encoding="utf-8"))
WEEK_START, WEEK_END = dt.date(2026, 11, 16), dt.date(2026, 11, 22)
STORE = StoreInfo(store_id="s1", name="테스트", lat=0, lng=0, open_time=dt.time(10), close_time=dt.time(22))


def at(text: str) -> dt.datetime:
    return dt.datetime.fromisoformat(text).replace(tzinfo=SEOUL)


def demo_orders() -> list[Order]:
    visits = {
        "c_w01": ["2026-10-21 18:10", "2026-10-28 18:20", "2026-11-04 18:30", "2026-11-11 18:20"],
        "c_m01": ["2026-07-23 19:00", "2026-08-21 19:00", "2026-09-25 19:00", "2026-10-23 19:00"],
    }
    return [
        Order(order_id=f"{key}_{i}", ordered_at=at(t), channel="DELIVERY", customer_key=key, total_amount=10000)
        for key, times in visits.items() for i, t in enumerate(times)
    ]


def demo_risk_signals() -> list[RiskSignalRow]:
    """데모 전 신호 3개(오래전에 끝남)에서 시작해 11/10~11/22 재계산 시각마다 위험 신호를 이어 간다."""
    earlier = [
        RiskSignalRow(risk_id=f"risk_{i:03d}", complaint_type="TASTE", review_ids=[f"old_{i}"], first_at=at(day),
                      last_at=at(day), detected_at=at(day), status="OPEN")
        for i, day in enumerate(["2026-08-25 13:50", "2026-09-10 13:50", "2026-10-05 13:50"], start=1)
    ]
    reviews = [Review.model_validate({**r, "label": None}) for r in RAW["reviews"]]
    labels = load_fixture("review_label")
    signals, day = earlier, dt.date(2026, 11, 10)
    while day <= WEEK_END:
        for t in (dt.time(9, 50), dt.time(13, 50), dt.time(21, 20)):
            signals = update_risk_signals(reviews, labels, signals, dt.datetime.combine(day, t, SEOUL))
        day += dt.timedelta(days=1)
    return [s for s in signals if s.risk_id not in {e.risk_id for e in earlier}]


def week_batches(result):
    return [b.model_dump() for b in result.batches if WEEK_START <= b.slot_at.date() <= WEEK_END]


def test_demo_risk_signal_after_whole_week_still_matches_fixture():
    assert demo_risk_signals() == load_fixture("risk_signal")


@pytest.mark.parametrize("now", ["2026-11-17T14:00:00+09:00", "2026-11-21T10:00:00+09:00", "2026-11-22T23:59:00+09:00"])
def test_analysis_results_give_same_demo_week_plan(now):
    now = dt.datetime.fromisoformat(now)
    cycles = build_customer_cycles(AnalysisInputs(store=STORE, orders=demo_orders()), at("2026-11-15 22:30"))
    inputs = PlanInputs.model_validate({
        **RAW,
        "customer_cycles": [row.model_dump(mode="json") for row in cycles],
        "risk_signals": [row.model_dump(mode="json") for row in demo_risk_signals()],
    })
    expected = make_plan(PlanInputs.model_validate(RAW), now)
    assert week_batches(make_plan(inputs, now)) == week_batches(expected)
