"""기준선: 특별한 칸을 뺀 최근 8주 같은 요일·시간대 칸 매출의 중앙값 (app/analysis/pattern/baseline.py)."""

import datetime as dt

import pytest

from app.analysis.mock_csv_reader import MOCK_DIR, read_mock_csv
from app.analysis.pattern.baseline import baseline_for, build_baselines
from app.analysis.pattern.sales_daily import build_sales_daily
from app.analysis.result_shapes import SalesDailyRow
from app.analysis.special_cells import cell_keys, find_special_cells
from app.core.seoul_time import SEOUL

MON = dt.date(2026, 11, 16)  # 월요일. 기준선을 구할 날
DAYPARTS = ["MORNING", "LUNCH", "DINNER"]


def row(day: dt.date, daypart: str, sales: int) -> SalesDailyRow:
    return SalesDailyRow(date=day, daypart=daypart, sales_amount=sales, qty=0, food_cost=None, labor_cost=None, profit=sales)


def weeks_before(day: dt.date, n: int) -> dt.date:
    return day - dt.timedelta(weeks=n)


def test_median_of_same_weekday_and_daypart_in_last_8_weeks():
    rows = [
        row(weeks_before(MON, 1), "LUNCH", 100),
        row(weeks_before(MON, 2), "LUNCH", 300),
        row(weeks_before(MON, 3), "LUNCH", 200),
        row(weeks_before(MON, 4), "LUNCH", 500),
        row(weeks_before(MON, 8), "LUNCH", 400),
        # 아래는 모두 쓰지 않는다
        row(weeks_before(MON, 9), "LUNCH", 9_000),  # 8주보다 오래됨
        row(MON, "LUNCH", 9_000),  # 기준선을 구하는 날 자신
        row(weeks_before(MON, 1) + dt.timedelta(days=1), "LUNCH", 9_000),  # 다른 요일
        row(weeks_before(MON, 1), "DINNER", 9_000),  # 다른 시간대
    ]
    assert baseline_for(rows, set(), MON, "LUNCH") == 300


def test_special_cells_are_left_out():
    rows = [row(weeks_before(MON, n), "DINNER", sales) for n, sales in [(1, 900), (2, 100), (3, 200), (4, 300), (5, 400)]]
    excluded = {(weeks_before(MON, 1), "DINNER")}  # 행사 칸 900원은 뺀다
    assert baseline_for(rows, excluded, MON, "DINNER") == 250


def test_fewer_than_4_weeks_left_gives_none():
    rows = [row(weeks_before(MON, n), "DINNER", 100) for n in (1, 2, 3, 4)]
    assert baseline_for(rows, set(), MON, "DINNER") == 100
    assert baseline_for(rows, {(weeks_before(MON, 4), "DINNER")}, MON, "DINNER") is None
    assert baseline_for([], set(), MON, "DINNER") is None


def test_even_count_median_rounds_half_up():
    # 가운데 두 값 10,001과 10,002의 평균 10,001.5 → 10,002 (짝수 쪽으로 보내는 round 라면 10,002, 내림이면 10,001)
    rows = [row(weeks_before(MON, n), "LUNCH", sales) for n, sales in [(1, 10_000), (2, 10_001), (3, 10_002), (4, 10_003)]]
    assert baseline_for(rows, set(), MON, "LUNCH") == 10_002
    # 10,000.5 → 10,001 (짝수 쪽으로 보내는 round 라면 10,000)
    rows = [row(weeks_before(MON, n), "LUNCH", sales) for n, sales in [(1, 9_000), (2, 10_000), (3, 10_001), (4, 11_000)]]
    assert baseline_for(rows, set(), MON, "LUNCH") == 10_001


def test_build_baselines_gives_every_weekday_and_daypart():
    as_of = dt.date(2026, 11, 18)  # 수요일. 11/11(수)~11/17(화)가 각 요일의 가장 최근 날
    rows = []
    for n in range(1, 9):
        for offset in range(7):
            day = as_of - dt.timedelta(days=1 + offset) - dt.timedelta(weeks=n - 1)
            rows.append(row(day, "LUNCH", 1_000 * n))  # 가장 최근 주가 1,000원, 8주 전이 8,000원
    rows.append(row(as_of, "LUNCH", 99_000))  # 기준일 당일은 넣지 않는다
    tue_lunch = (as_of - dt.timedelta(days=1), "LUNCH")

    result = build_baselines(rows, {tue_lunch}, as_of, DAYPARTS)

    assert len(result) == 21
    assert result[("WED", "LUNCH")] == 4_500  # 1,000~8,000의 중앙값
    assert result[("TUE", "LUNCH")] == 5_000  # 가장 최근 화요일(1,000원)은 뺀 칸 → 2,000~8,000의 중앙값
    assert result[("MON", "MORNING")] is None  # 아침 매출 행이 없다


# ── 목업 데이터: N2 완료 기준 (21칸 모두 나오고, 손으로 계산한 3칸과 같다) ──


@pytest.mark.skipif(not (MOCK_DIR / "orders.csv").exists(), reason="목업 CSV 가 없다")
def test_mock_baselines_cover_21_cells_and_match_hand_calculation():
    now = dt.datetime(2026, 11, 17, 22, 30, tzinfo=SEOUL)
    inputs = read_mock_csv()
    rows = build_sales_daily(inputs, now).rows
    excluded = cell_keys(find_special_cells(inputs, rows[0].date, now.date()))

    result = build_baselines(rows, excluded, dt.date(2026, 11, 18), DAYPARTS)

    assert len(result) == 21 and all(value is not None for value in result.values())
    # 원본 orders.csv 를 직접 더해 계산했다
    assert result[("WED", "DINNER")] == 637_250  # 9/23·9/30·10/14·10/28 빼고 4주: (620,500 + 654,000) / 2
    assert result[("THU", "LUNCH")] == 859_000  # 9/24·10/8·11/5 빼고 5주의 가운데
    assert result[("TUE", "DINNER")] == 731_250  # 10/20·10/27 빼고 6주: (727,500 + 735,000) / 2


def test_zero_sales_cells_count_as_real_results():
    rows = [row(weeks_before(MON, n), "MORNING", sales) for n, sales in [(1, 0), (2, 0), (3, 0), (4, 40_000), (5, 50_000)]]
    assert baseline_for(rows, set(), MON, "MORNING") == 0
