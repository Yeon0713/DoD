"""메뉴판 기준 태그와 '바뀌는 것 없음' 판정 테스트. server/ 폴더에서 `python -m pytest` 로 실행한다."""

import datetime as dt
import json
from pathlib import Path

from app.analysis.store_calendar.season import season_ref_id
from app.planner.data_shapes import CalendarReason, PlanInputs
from app.planner.rule_menu_order import TagPeriod, menu_board_bases, plan_menu_orders, unchanged_menu_orders

SAMPLE_INPUTS = Path(__file__).parent / "sample_inputs" / "demo_week_inputs.example.json"
INPUTS = PlanInputs.model_validate(json.loads(SAMPLE_INPUTS.read_text(encoding="utf-8")))
STORE = INPUTS.store
K = 2  # 교체 부담 0.1 × 2 = 0.2

# 데모 주간의 원본 일정: 겨울은 11/18 시작(아직 안 끝남), 국가대표 경기 11/19, 축제 11/21~22
PERIODS = [
    TagPeriod("season_winter", dt.date(2026, 11, 18)),
    TagPeriod("game_031", dt.date(2026, 11, 19), dt.date(2026, 11, 19)),
    TagPeriod("event_012", dt.date(2026, 11, 21), dt.date(2026, 11, 22)),
]


def d(day: int) -> dt.date:
    return dt.date(2026, 11, day)


def test_demo_week_bases_follow_the_strongest_worthwhile_tag():
    bases = menu_board_bases(INPUTS.calendar, PERIODS, STORE, K)
    assert bases == {
        d(15): None,
        d(16): None,
        d(17): None,
        d(18): "season_winter",  # 겨울 0.05 × 6일 = 0.30 > 0.2
        d(19): "game_031",  # 경기 0.23 × 1일 = 0.23 > 0.2, 하루 효과 0.23 > 겨울 0.05
        d(20): "season_winter",
        d(21): "event_012",  # 축제 0.30 × 2일 = 0.60
        d(22): "event_012",
        d(23): "season_winter",  # 축제가 끝나도 겨울이 남는다
    }


def with_effect(calendar, ref_id: str, effect: float):
    """그 근거 id가 붙은 모든 칸의 효과를 바꾼 달력"""
    def changed(reason):
        return reason.model_copy(update={"effect": effect}) if reason.ref_id == ref_id else reason
    return [cell.model_copy(update={"reasons": [changed(r) for r in cell.reasons]}) for cell in calendar]


def with_reason(calendar, days: set[dt.date], reason: CalendarReason):
    """그날들의 모든 칸에 이유를 더한 달력"""
    return [cell.model_copy(update={"reasons": [*cell.reasons, reason]}) if cell.date in days else cell for cell in calendar]


def test_small_festival_is_not_worth_switching():
    calendar = with_effect(INPUTS.calendar, "event_012", 0.08)  # 0.08 × 2일 = 0.16 < 0.2
    bases = menu_board_bases(calendar, PERIODS, STORE, K)
    assert bases[d(21)] == bases[d(22)] == "season_winter"


def test_benefit_equal_to_burden_is_not_enough():
    calendar = with_effect(INPUTS.calendar, "event_012", 0.1)  # 0.1 × 2일 = 0.2
    bases = menu_board_bases(calendar, PERIODS, STORE, K)
    assert bases[d(21)] == "season_winter"

    # 세 시간대 0.2의 평균은 부동소수로 0.20000000000000004 가 되지만 같은 것으로 본다
    game = CalendarReason(tag="GAME", ref_id="game_040", effect=0.2)
    calendar = with_reason(INPUTS.calendar, {d(17)}, game)
    bases = menu_board_bases(calendar, [*PERIODS, TagPeriod("game_040", d(17), d(17))], STORE, K)
    assert bases[d(17)] is None


def test_one_day_game_needs_a_large_enough_effect():
    weak = menu_board_bases(with_effect(INPUTS.calendar, "game_031", 0.15), PERIODS, STORE, K)
    strong = menu_board_bases(with_effect(INPUTS.calendar, "game_031", 0.25), PERIODS, STORE, K)
    assert weak[d(19)] == "season_winter"  # 0.15 × 1일 < 0.2
    assert strong[d(19)] == "game_031"  # 0.25 × 1일 > 0.2


def test_equal_daily_effects_are_broken_by_ref_id():
    rival = CalendarReason(tag="EVENT", ref_id="event_011", effect=0.3)  # 같은 날 같은 효과의 다른 행사
    calendar = with_reason(INPUTS.calendar, {d(21), d(22)}, rival)
    periods = [*PERIODS, TagPeriod("event_011", d(21), d(22))]
    bases = menu_board_bases(calendar, periods, STORE, K)
    assert bases[d(21)] == bases[d(22)] == "event_011"


def test_equal_daily_effects_on_different_numbers_of_cells_are_still_equal():
    # 0.1 세 칸의 평균은 부동소수로 0.10000000000000002 가 되지만 한 칸 0.1 과 같은 것으로 본다
    calendar = with_effect(INPUTS.calendar, "game_031", 0.1)  # 저녁·밤 두 칸
    all_day = CalendarReason(tag="GAME", ref_id="game_099", effect=0.1)
    calendar = with_reason(calendar, {d(19)}, all_day)  # 같은 날 세 칸 모두
    periods = [*PERIODS, TagPeriod("game_099", d(19), d(19))]
    bases = menu_board_bases(calendar, periods, STORE, k=0)  # 부담 0: 둘 다 바꿀 만하다
    assert bases[d(19)] == "game_031"  # 근거 id 순


def test_closed_day_does_not_cut_the_period():
    store = STORE.model_copy(update={"closed_weekdays": ["SAT"]})  # 축제 첫날 11/21(토) 휴무
    calendar = [cell for cell in with_effect(INPUTS.calendar, "event_012", 0.11) if cell.date != d(21)]
    periods = [*PERIODS[:2], TagPeriod("event_012", d(20), d(22))]  # 금~일 축제, 영업일은 금·일 2일
    bases = menu_board_bases(calendar, periods, store, K)
    assert d(21) not in bases
    assert bases[d(22)] == "event_012"  # 0.11 × 2일 = 0.22 > 0.2. 토요일에서 끊겼다면 하루뿐이라 탈락


def test_season_period_matches_calendar_ref_id():
    assert season_ref_id("WINTER") == "season_winter"  # 달력 칸의 계절 근거 id와 같은 값
    started_early = [TagPeriod(season_ref_id("WINTER"), d(1)), *PERIODS[1:]]  # 11/1부터 겨울 23일
    bases = menu_board_bases(INPUTS.calendar, started_early, STORE, k=5)  # 부담 0.5
    assert bases[d(18)] == "season_winter"  # 0.05 × 23일 = 1.15. 달력에 보인 6일만 세면 0.30이라 탈락


def test_every_demo_week_card_changes_the_board():
    cards = plan_menu_orders(INPUTS.calendar, STORE)  # 18 계절, 19 경기, 20 경기 끝, 21 축제, 23 축제 끝
    bases = menu_board_bases(INPUTS.calendar, PERIODS, STORE, K)
    assert unchanged_menu_orders(cards, bases, STORE) == set()


def test_cards_for_a_festival_filtered_by_benefit_change_nothing():
    calendar = with_effect(INPUTS.calendar, "event_012", 0.08)  # 축제는 교체 이득이 부담을 넘지 못해 21~23 모두 겨울 배치
    cards = plan_menu_orders(calendar, STORE)
    bases = menu_board_bases(calendar, PERIODS, STORE, K)
    assert unchanged_menu_orders(cards, bases, STORE) == {
        "MENU_ORDER:2026-11-21:2026-11-21",  # 축제 시작 카드
        "MENU_ORDER:2026-11-23:2026-11-23",  # 축제 끝 카드
    }
