"""contracts/fixtures/analysis/ 고정 샘플 점검.

1. 모든 파일이 app/analysis/result_shapes.py 의 모양으로 읽히는지
2. 시각·날짜 형식, 키 중복, 계산 규칙, 테이블끼리 값이 맞는지
3. 고정 샘플로 계획 엔진을 돌린 결과가 tests/planner/sample_inputs/ 의 입력으로 돌린 결과와 같은지

server/ 폴더에서 `python -m pytest tests/analysis -v` 로 실행한다.
"""

import datetime as dt
import json
import re
from collections import Counter
from pathlib import Path

import pytest

from app.analysis.result_shapes import RESULT_TABLES, load_fixture, load_fixture_raw
from app.planner.data_shapes import PlanInputs
from app.planner.make_plan import make_plan

PLANNER_INPUTS = Path(__file__).parents[1] / "planner" / "sample_inputs" / "demo_week_inputs.example.json"
DATETIME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+09:00$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
DATETIME_FIELDS = {"computed_at", "next_expected_at", "labeled_at", "first_at", "last_at", "detected_at"}
GROUP_OF = {
    "TASTE": "FOOD", "PORTION": "FOOD", "HYGIENE": "FOOD", "PHOTO_MISMATCH": "FOOD",
    "DELIVERY_DELAY": "DELIVERY", "SERVICE": "SERVICE",
}


def planner_inputs_raw() -> dict:
    return json.loads(PLANNER_INPUTS.read_text(encoding="utf-8"))


@pytest.mark.parametrize("table", RESULT_TABLES)
def test_fixture_matches_shape(table):
    rows = load_fixture(table)
    assert rows, f"{table} 고정 샘플이 비어 있습니다."


@pytest.mark.parametrize("table", RESULT_TABLES)
def test_times_are_seoul_iso(table):
    """시각은 +09:00 이 붙은 ISO 8601, 날짜는 YYYY-MM-DD."""
    for row in load_fixture_raw(table):
        for key, value in row.items():
            if key in DATETIME_FIELDS and value is not None:
                assert DATETIME_RE.match(value), f"{table}.{key} = {value} (+09:00 형식이 아님)"
            if key == "date":
                assert DATE_RE.match(value), f"{table}.date = {value}"


def test_keys_are_unique():
    keys = {
        "sales_daily": lambda r: (r.date, r.daypart),
        "calendar_day": lambda r: (r.date, r.daypart, r.computed_at),
        "customer_cycle": lambda r: (r.customer_key, r.computed_at),
        "review_label": lambda r: r.review_id,
        "risk_signal": lambda r: r.risk_id,
        "sales_anomaly": lambda r: (r.date, r.daypart),
    }
    for table, key in keys.items():
        counts = Counter(key(row) for row in load_fixture(table))
        duplicated = [k for k, n in counts.items() if n > 1]
        assert not duplicated, f"{table} 키 중복: {duplicated}"


def test_review_label_groups_follow_rule():
    """불만 묶음은 불만 유형에서 정해지고, 묶음이 하나라도 있으면 is_quick 이다."""
    for row in load_fixture("review_label"):
        groups = sorted({GROUP_OF[t] for t in row.complaint_types})
        assert sorted(row.complaint_groups) == groups, row.review_id
        assert row.is_quick == bool(groups), row.review_id


def test_review_label_points_to_known_reviews():
    """분류 결과와 위험 신호의 review_id 가 원본 리뷰에 있다."""
    review_ids = {r["review_id"] for r in planner_inputs_raw()["reviews"]}
    for row in load_fixture("review_label"):
        assert row.review_id in review_ids, f"{row.review_id} 원본 리뷰가 없습니다."
    for risk in load_fixture("risk_signal"):
        assert set(risk.review_ids) <= review_ids, risk.risk_id


def test_customer_cycles_follow_cycle_rule():
    """WEEKLY 는 최근 3개 간격 중 2개 이상이 5~9일, MONTHLY 는 25~35일. NONE 은 다음 예상 시점이 없다."""
    for row in load_fixture("customer_cycle"):
        last3 = row.intervals_days[-3:]
        if row.cycle == "WEEKLY":
            assert sum(5 <= d <= 9 for d in last3) >= 2, row.customer_key
        elif row.cycle == "MONTHLY":
            assert len(last3) == 3 and sum(25 <= d <= 35 for d in last3) >= 2, row.customer_key
        else:
            assert row.next_expected_at is None and row.expected_daypart is None, row.customer_key


def test_sales_anomaly_matches_sales_daily_and_calendar():
    """매출 이상의 실제 매출은 sales_daily, 기준선은 calendar_day 의 같은 칸 값이다."""
    sales = {(r.date, r.daypart): r for r in load_fixture("sales_daily")}
    calendar = {(r.date, r.daypart): r for r in load_fixture("calendar_day")}
    for anomaly in load_fixture("sales_anomaly"):
        key = (anomaly.date, anomaly.daypart)
        assert sales[key].sales_amount == anomaly.actual_sales
        assert calendar[key].baseline_sales == anomaly.baseline_sales
        assert round(anomaly.actual_sales / anomaly.baseline_sales, 2) == anomaly.ratio


def test_calendar_ratio_and_signal():
    """예상 매출 = 기준선 × (1 + 효과 합), 비율 1.15 이상 HIGH, 0.85 이하 LOW, 나머지 NORMAL."""
    for cell in load_fixture("calendar_day"):
        effect = sum(reason.effect for reason in cell.reasons)
        assert cell.expected_sales == round(cell.baseline_sales * (1 + effect)), (cell.date, cell.daypart)
        assert cell.ratio == round(cell.expected_sales / cell.baseline_sales, 2), (cell.date, cell.daypart)
        expected_signal = "HIGH" if cell.ratio >= 1.15 else "LOW" if cell.ratio <= 0.85 else "NORMAL"
        assert cell.signal == expected_signal, (cell.date, cell.daypart)


def inputs_from_fixtures() -> PlanInputs:
    """매장 설정, 리뷰 본문, 행사, 경기는 계획 엔진 테스트 입력에서, 분석 결과는 고정 샘플에서 가져온다."""
    raw = planner_inputs_raw()
    labels = {row.review_id: row.to_label().model_dump(mode="json") for row in load_fixture("review_label")}
    reviews = [{**review, "label": labels.get(review["review_id"])} for review in raw["reviews"]]
    return PlanInputs.model_validate({
        "store": raw["store"],
        "events": raw["events"],
        "games": raw["games"],
        "reviews": reviews,
        "customer_cycles": load_fixture_raw("customer_cycle"),
        "calendar": load_fixture_raw("calendar_day"),
        "risk_signals": load_fixture_raw("risk_signal"),
        "sales_anomalies": load_fixture_raw("sales_anomaly"),
    })


@pytest.mark.parametrize("now", [
    "2026-11-16T10:00:00+09:00",
    "2026-11-17T14:00:00+09:00",
    "2026-11-20T21:30:00+09:00",
    "2026-11-22T23:59:00+09:00",
])
def test_fixtures_give_same_plan_as_planner_inputs(now):
    """계획 엔진 결과(할 일, 알림, 알림 묶음)가 계획 엔진 테스트 입력으로 돌린 결과와 같다."""
    now = dt.datetime.fromisoformat(now)
    ours = make_plan(inputs_from_fixtures(), now)
    theirs = make_plan(PlanInputs.model_validate(planner_inputs_raw()), now)
    assert ours.model_dump() == theirs.model_dump()
