"""과거 효과 (app/analysis/store_calendar/past_effects.py).

효과는 같은 묶음(행사 종류·경기 종류·날씨 종류)의 과거 특별한 칸에서 실제 매출이 기준선과 달랐던 비율의 평균이다.
시간대마다 따로 본다.
"""

import datetime as dt
from pathlib import Path

import pytest

from app.analysis.input_shapes import AnalysisInputs, StoreInfo
from app.analysis.mock_csv_reader import read_mock_csv
from app.analysis.pattern.sales_daily import build_sales_daily
from app.analysis.result_shapes import SalesDailyRow
from app.analysis.store_calendar.past_effects import PastEffect, build_past_effects, tagged_effect
from app.core.seoul_time import SEOUL
from app.planner.data_shapes import Event, Game

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "mock_v1"  # 손계산 기대값을 계산한 목업 v1 (고정)
STORE = StoreInfo(store_id="s1", name="테스트", lat=0, lng=0, open_time=dt.time(10), close_time=dt.time(22))
MON = dt.date(2026, 11, 2)  # 월요일. 과거 사례가 생기는 날
DAYPARTS = ("MORNING", "LUNCH", "DINNER")
NOW = dt.datetime(2026, 12, 1, 22, 30, tzinfo=SEOUL)


def at(day: dt.date, hour: int, minute: int = 0) -> dt.datetime:
    return dt.datetime(day.year, day.month, day.day, hour, minute, tzinfo=SEOUL)


def weeks(n: int) -> dt.date:
    return MON + dt.timedelta(weeks=n)


def row(day: dt.date, daypart: str, amount: int) -> SalesDailyRow:
    return SalesDailyRow(date=day, daypart=daypart, sales_amount=amount, qty=0, food_cost=None, labor_cost=None, profit=amount)


def mondays(sales: dict[tuple[dt.date, str], int], first_week: int = -8, last_week: int = 3) -> list[SalesDailyRow]:
    """월요일마다 세 시간대 행. 따로 정하지 않은 칸은 100원."""
    return [
        row(day, p, sales.get((day, p), 100))
        for n in range(first_week, last_week + 1)
        for day in [weeks(n)]
        for p in DAYPARTS
    ]


def event(event_id: str, kind: str, start: dt.datetime, end: dt.datetime) -> Event:
    return Event(event_id=event_id, kind=kind, title="행사", start_at=start, end_at=end, distance_km=0.5)


def test_effects_are_averaged_per_kind_and_daypart():
    inputs = AnalysisInputs(
        store=STORE,
        events=[
            event("event_001", "LOCAL_FESTIVAL", at(weeks(0), 12), at(weeks(0), 13)),  # 점심만
            event("event_002", "LOCAL_FESTIVAL", at(weeks(1), 12), at(weeks(1), 13)),
            event("event_003", "UNIV_FESTIVAL", at(weeks(2), 12), at(weeks(2), 13)),
        ],
    )
    rows = mondays({(weeks(0), "LUNCH"): 150, (weeks(1), "LUNCH"): 130, (weeks(2), "LUNCH"): 80})

    effects = build_past_effects(inputs, rows, NOW)

    # 기준선은 모두 100원(같은 요일 다른 주, 특별한 칸 제외)
    assert effects[(("EVENT", "LOCAL_FESTIVAL"), "LUNCH")] == PastEffect(effect=pytest.approx(0.4), cell_count=2)  # (+0.5 + 0.3) / 2
    assert effects[(("EVENT", "UNIV_FESTIVAL"), "LUNCH")] == PastEffect(effect=pytest.approx(-0.2), cell_count=1)
    assert (("EVENT", "LOCAL_FESTIVAL"), "DINNER") not in effects  # 저녁 칸은 행사와 안 겹친다


def test_a_cell_with_two_reasons_counts_for_both_groups():
    """원인을 나눌 수 없어서 겹친 칸의 효과는 두 묶음에 모두 들어간다."""
    inputs = AnalysisInputs(
        store=STORE,
        events=[event("event_001", "LOCAL_FESTIVAL", at(weeks(0), 12), at(weeks(0), 13))],
        games=[Game(game_id="game_001", kind="BASEBALL", title="야구", start_at=at(weeks(0), 12))],  # 점심 시작 → 점심·저녁
    )
    rows = mondays({(weeks(0), "LUNCH"): 160, (weeks(0), "DINNER"): 120})

    effects = build_past_effects(inputs, rows, NOW)

    assert effects[(("EVENT", "LOCAL_FESTIVAL"), "LUNCH")].effect == pytest.approx(0.6)
    assert effects[(("GAME", "BASEBALL"), "LUNCH")].effect == pytest.approx(0.6)
    assert effects[(("GAME", "BASEBALL"), "DINNER")].effect == pytest.approx(0.2)


def test_falls_back_to_all_days_of_the_daypart_when_the_weekday_baseline_is_missing():
    """같은 요일 칸이 4주 미만이면, 과거 효과에서만 직전 8주 같은 시간대의 모든 날(특별한 칸 제외) 중앙값을 쓴다."""
    tue, wed, thu = (weeks(-1) + dt.timedelta(days=d) for d in (1, 2, 3))  # 지난주 화·수·목
    rows = [
        row(weeks(-3), "LUNCH", 100),  # 이 칸은 앞선 기록이 없어 어떤 기준선도 없다 → 사례에서 빠진다
        row(weeks(-2), "LUNCH", 100),
        row(weeks(-1), "LUNCH", 100),
        row(tue, "LUNCH", 200),
        row(wed, "LUNCH", 200),
        row(thu, "LUNCH", 9_000),  # 특별한 칸이라 대체 기준선에서도 뺀다
        row(weeks(0), "LUNCH", 300),
    ]
    inputs = AnalysisInputs(
        store=STORE,
        events=[
            event("event_001", "LOCAL_FESTIVAL", at(weeks(0), 12), at(weeks(0), 13)),
            event("event_002", "UNIV_FESTIVAL", at(weeks(-3), 12), at(weeks(-3), 13)),
            event("event_003", "MARATHON", at(thu, 12), at(thu, 13)),
        ],
    )

    effects = build_past_effects(inputs, rows, NOW)

    # 같은 요일은 2주뿐이다. 대체 기준선: 100·100·200·200 의 중앙값 150 → 300 / 150 − 1
    # (목요일 9,000원을 빼지 않으면 중앙값이 200 이 되어 +0.5 가 나온다)
    assert effects[(("EVENT", "LOCAL_FESTIVAL"), "LUNCH")] == PastEffect(effect=pytest.approx(1.0), cell_count=1)
    assert (("EVENT", "UNIV_FESTIVAL"), "LUNCH") not in effects


def test_cells_after_now_or_without_sales_are_not_used():
    rows = [r for r in mondays({(weeks(0), "LUNCH"): 150, (weeks(1), "LUNCH"): 999}) if r.date != weeks(2)]  # 2주 뒤 매출 행 없음
    inputs = AnalysisInputs(
        store=STORE,
        events=[
            event("event_001", "LOCAL_FESTIVAL", at(weeks(0), 12), at(weeks(0), 13)),
            event("event_002", "LOCAL_FESTIVAL", at(weeks(1), 12), at(weeks(1), 13)),  # now 이후
            event("event_003", "LOCAL_FESTIVAL", at(weeks(2), 12), at(weeks(2), 13)),  # 매출 행이 없다
        ],
    )
    now = at(weeks(0), 22, 30)

    effects = build_past_effects(inputs, rows, now)

    assert effects[(("EVENT", "LOCAL_FESTIVAL"), "LUNCH")] == PastEffect(effect=pytest.approx(0.5), cell_count=1)


def test_only_effects_of_10_percent_or_more_get_a_tag():
    festival, rain = ("EVENT", "LOCAL_FESTIVAL"), ("WEATHER", "RAIN")
    effects = {
        (festival, "LUNCH"): PastEffect(effect=0.10, cell_count=2),  # 정확히 10% 는 태그
        (festival, "DINNER"): PastEffect(effect=0.099, cell_count=2),
        (rain, "MORNING"): PastEffect(effect=-0.10, cell_count=6),
        (rain, "LUNCH"): PastEffect(effect=-0.076, cell_count=12),
    }
    assert tagged_effect(effects, festival, "LUNCH") == 0.10
    assert tagged_effect(effects, festival, "DINNER") is None
    assert tagged_effect(effects, rain, "MORNING") == -0.10
    assert tagged_effect(effects, rain, "LUNCH") is None
    assert tagged_effect(effects, festival, "MORNING") is None  # 사례가 없다


# ── 목업 데이터 (원본 CSV 손 계산과 비교. 효과값은 정확한 숫자로 고정하지 않는다) ──


def test_mock_past_effects_match_hand_calculation_in_tags():
    inputs = read_mock_csv(FIXTURE_DIR)
    now = dt.datetime(2026, 11, 17, 22, 30, tzinfo=SEOUL)
    effects = build_past_effects(inputs, build_sales_daily(inputs, now).rows, now)

    national = effects[(("GAME", "NATIONAL_TEAM"), "DINNER")]
    assert national.cell_count == 1  # 10/14 한 경기뿐이다(표본 1칸). 같은 요일 기준선이 없어 대체 기준선을 쓴다
    assert tagged_effect(effects, ("GAME", "NATIONAL_TEAM"), "DINNER") > 0  # 손 계산 +35.1%

    assert effects[(("GAME", "BASEBALL"), "DINNER")].cell_count == 6
    assert tagged_effect(effects, ("GAME", "BASEBALL"), "DINNER") is None  # 손 계산 +6.5%

    assert tagged_effect(effects, ("EVENT", "LOCAL_FESTIVAL"), "LUNCH") > 0  # 손 계산 +17.6%
    assert tagged_effect(effects, ("EVENT", "LOCAL_FESTIVAL"), "DINNER") > 0  # 손 계산 +49.3%
    assert tagged_effect(effects, ("WEATHER", "RAIN"), "MORNING") < 0  # 손 계산 −13.2%. 아침은 매출이 작아 크게 흔들린다
    assert tagged_effect(effects, ("WEATHER", "RAIN"), "LUNCH") is None  # 손 계산 −7.6%
