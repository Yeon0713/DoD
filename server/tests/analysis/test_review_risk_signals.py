"""위험 신호 (app/analysis/review/risk_signals.py).

데모 리뷰는 tests/planner/sample_inputs/demo_week_inputs.example.json, 분류 결과는 contracts 고정 샘플을 쓴다.
"""

import datetime as dt
import json
from pathlib import Path

import pytest

from app.analysis.mock_csv_reader import MOCK_DIR, read_mock_csv
from app.analysis.result_shapes import ReviewLabelRow, RiskSignalRow, load_fixture
from app.analysis.review.label_reviews import label_reviews
from app.analysis.review.risk_signals import update_risk_signals
from app.core.seoul_time import SEOUL
from app.planner.data_shapes import Review

PLANNER_INPUTS = Path(__file__).parents[1] / "planner" / "sample_inputs" / "demo_week_inputs.example.json"
DEMO_REVIEWS = [Review.model_validate({**r, "label": None}) for r in json.loads(PLANNER_INPUTS.read_text(encoding="utf-8"))["reviews"]]
DEMO_LABELS = load_fixture("review_label")


def at(text: str) -> dt.datetime:
    return dt.datetime.fromisoformat(text).replace(tzinfo=SEOUL)


# 데모 이전에 이미 있던 신호 3개 (오래전에 끝남)
EARLIER = [
    RiskSignalRow(risk_id=f"risk_{i:03d}", complaint_type=kind, review_ids=[f"old_{i}"], first_at=at(day), last_at=at(day),
                  detected_at=at(day), status="OPEN")
    for i, (kind, day) in enumerate([("TASTE", "2026-08-25 13:50"), ("DELIVERY_DELAY", "2026-09-10 13:50"), ("TASTE", "2026-10-05 13:50")], start=1)
]


def recompute_times(start: dt.date, end: dt.date) -> list[dt.datetime]:
    """알림 시각(10:00, 14:00, 21:30) 10분 전 재계산 시각."""
    times, day = [], start
    while day <= end:
        times += [dt.datetime.combine(day, t, SEOUL) for t in (dt.time(9, 50), dt.time(13, 50), dt.time(21, 20))]
        day += dt.timedelta(days=1)
    return times


def replay(reviews, labels, previous, times):
    signals = previous
    for now in times:
        signals = update_risk_signals(reviews, labels, signals, now)
    return signals


def label(review_id: str, types: list[str], labeled: str) -> ReviewLabelRow:
    return ReviewLabelRow(review_id=review_id, sentiment="NEGATIVE", complaint_types=types, complaint_groups=[],
                          is_quick=bool(types), labeler="RULE", labeled_at=at(labeled))


def review(review_id: str, written: str) -> Review:
    return Review(review_id=review_id, platform="BAEMIN", written_at=at(written), rating=2, text="불만")


def test_demo_delivery_delay_opens_risk_004_at_1350_and_matches_fixture():
    signals = replay(DEMO_REVIEWS, DEMO_LABELS, EARLIER, recompute_times(dt.date(2026, 11, 10), dt.date(2026, 11, 17))[:-1])
    new = [s for s in signals if s.risk_id not in {e.risk_id for e in EARLIER}]
    assert new == load_fixture("risk_signal")


def test_two_complaints_are_not_enough():
    signals = update_risk_signals(DEMO_REVIEWS, DEMO_LABELS, EARLIER, at("2026-11-15 21:20"))
    assert signals == EARLIER


def test_open_signal_gets_new_reviews_without_changing_id_or_detected_at():
    reviews = [review("a", "2026-11-01 12:00"), review("b", "2026-11-02 12:00"), review("c", "2026-11-03 12:00"), review("d", "2026-11-06 12:00")]
    labels = [label(r.review_id, ["SERVICE"], "2026-11-03 13:00") for r in reviews[:3]] + [label("d", ["SERVICE"], "2026-11-06 13:00")]
    opened = update_risk_signals(reviews[:3], labels, [], at("2026-11-03 13:50"))
    grown = update_risk_signals(reviews, labels, opened, at("2026-11-06 13:50"))
    assert len(grown) == 1
    assert (grown[0].risk_id, grown[0].detected_at) == (opened[0].risk_id, opened[0].detected_at)
    assert grown[0].review_ids == ["a", "b", "c", "d"] and grown[0].last_at == at("2026-11-06 12:00")


def test_quiet_for_seven_days_then_new_signal():
    first = [review(f"a{i}", f"2026-10-0{i} 12:00") for i in (1, 2, 3)]
    second = [review(f"b{i}", f"2026-10-2{i} 12:00") for i in (1, 2, 3)]
    labels = [label(r.review_id, ["TASTE"], "2026-10-01 00:00") for r in first + second]
    signals = update_risk_signals(first, labels, [], at("2026-10-03 13:50"))
    signals = update_risk_signals(first + second, labels, signals, at("2026-10-23 13:50"))
    assert [s.risk_id for s in signals] == ["risk_001", "risk_002"]
    assert signals[1].review_ids == ["b1", "b2", "b3"]


def test_review_with_two_types_counts_for_both():
    reviews = [review(f"r{i}", f"2026-11-0{i} 12:00") for i in (1, 2, 3)]
    labels = [label(r.review_id, ["TASTE", "DELIVERY_DELAY"], "2026-11-03 13:00") for r in reviews]
    signals = update_risk_signals(reviews, labels, [], at("2026-11-03 13:50"))
    assert [(s.risk_id, s.complaint_type) for s in signals] == [("risk_001", "TASTE"), ("risk_002", "DELIVERY_DELAY")]


def test_labels_made_after_now_are_not_used():
    reviews = [review(f"r{i}", f"2026-11-0{i} 12:00") for i in (1, 2, 3)]
    labels = [label(r.review_id, ["TASTE"], "2026-11-03 21:20") for r in reviews]
    assert update_risk_signals(reviews, labels, [], at("2026-11-03 13:50")) == []


def test_reviews_older_than_seven_days_do_not_open():
    reviews = [review("r1", "2026-11-01 12:00"), review("r2", "2026-11-07 12:00"), review("r3", "2026-11-09 12:00")]
    labels = [label(r.review_id, ["TASTE"], "2026-11-09 13:00") for r in reviews]
    assert update_risk_signals(reviews, labels, [], at("2026-11-09 13:50")) == []


@pytest.mark.skipif(not (MOCK_DIR / "reviews.csv").exists(), reason="목업 CSV 가 없다")
def test_mock_history_opens_each_burst_once():
    """목업 리뷰를 재계산 시각마다 키워드 규칙으로 분류하고 위험 신호를 이어 가도, 한 리뷰가 두 신호에 들어가지 않는다."""
    reviews = read_mock_csv().reviews
    labels, signals = [], []
    for now in recompute_times(dt.date(2026, 8, 17), dt.date(2026, 11, 15)):
        labeled = {row.review_id for row in labels}
        labels += label_reviews([r for r in reviews if r.review_id not in labeled], now, classifier=None)
        signals = update_risk_signals(reviews, labels, signals, now)
    assert signals, "목업 이력에서 위험 신호가 하나도 열리지 않았다"
    assert [s.risk_id for s in signals] == [f"risk_{i:03d}" for i in range(1, len(signals) + 1)]
    for kind in {s.complaint_type for s in signals}:
        ids = [rid for s in signals if s.complaint_type == kind for rid in s.review_ids]
        assert len(ids) == len(set(ids))
    for s in signals:
        assert len(s.review_ids) >= 3 and s.first_at <= s.detected_at and s.first_at <= s.last_at
