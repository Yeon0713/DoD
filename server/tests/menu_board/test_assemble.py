"""메뉴판 카드 조립 테스트. server/ 폴더에서 `python -m pytest` 로 실행한다.

데모 주간(11/18 겨울 시작, 11/19 국가대표 경기, 11/21~22 축제)의 달력·매장 설정·행사·경기는 계획 엔진 예시 입력을 쓰고,
분석 입력(주문, 메뉴, 날씨)은 여기서 만든다. LLM 후보는 가짜 조회 함수로 넣는다.
"""

import datetime as dt
import itertools
import json
import logging
from collections import Counter
from pathlib import Path

import pytest

from app.analysis.input_shapes import AnalysisInputs, DaypartRange, Menu, Order, OrderItem, StoreInfo, WeatherDay
from app.core.config import settings
from app.core.seoul_time import SEOUL
from app.data_pipeline import store_snapshot_cache
from app.data_pipeline.menu_original_order import original_menu_order
from app.menu_board.arrangement import NO_PICK_REASON
from app.menu_board.assemble import BACK_TO_ORIGINAL_REASON, UNCHANGED_REASON
from app.menu_board.assemble import assemble_menu_board_cards, tag_periods_from_inputs
from app.menu_board.menu_candidates import EMPTY, MenuCandidates
from app.planner.data_shapes import CalendarReason, Event, PlanInputs
from app.planner.rule_menu_order import TagPeriod, plan_menu_orders

SAMPLE_INPUTS = Path(__file__).parents[1] / "planner" / "sample_inputs" / "demo_week_inputs.example.json"
PLAN = PlanInputs.model_validate(json.loads(SAMPLE_INPUTS.read_text(encoding="utf-8")))
SETTINGS = PLAN.store
STORE = {"store_id": "store_001", "name": "데모 국숫집", "category": "국수"}
ORIGINAL = [Menu(menu_id=m, name=n, category="MAIN", price=9000) for m, n in [("1", "국수"), ("2", "비빔국수"), ("3", "만두"), ("4", "전"), ("5", "수육")]]
ANALYSIS_STORE = StoreInfo(
    store_id="store_001",
    name="데모 국숫집",
    lat=37.0,
    lng=127.0,
    open_time=dt.time(10),
    close_time=dt.time(22),
    dayparts=[
        DaypartRange(daypart="LUNCH", start=dt.time(11), end=dt.time(13, 30)),
        DaypartRange(daypart="DINNER", start=dt.time(17), end=dt.time(21)),
        DaypartRange(daypart="NIGHT", start=dt.time(21), end=dt.time(22)),
    ],
)
PAST_FESTIVAL = dt.date(2026, 10, 24)
_order_ids = itertools.count(1)

WINTER_REASON = "추운 날엔 수육과 만두가 잘 어울려요"
FESTIVAL_REASON = "축제엔 나눠 먹기 좋은 전이 잘 어울려요"


def d(day: int) -> dt.date:
    return dt.date(2026, 11, day)


def days(first: dt.date, last: dt.date) -> list[dt.date]:
    return [first + dt.timedelta(days=i) for i in range((last - first).days + 1)]


def lunch(day: dt.date, qty: dict[str, int]) -> tuple[Order, list[OrderItem]]:
    order_id = f"o{next(_order_ids)}"
    order = Order(order_id=order_id, ordered_at=dt.datetime.combine(day, dt.time(12), tzinfo=SEOUL), channel="HALL", total_amount=0)
    return order, [OrderItem(order_id=order_id, menu_id=m, quantity=q, unit_price=9000) for m, q in qty.items()]


def weather() -> list[WeatherDay]:
    """1~2월 겨울(작년이 아니라 올해 초 겨울), 3월~11/17 15도, 11/18 부터 다시 겨울"""
    def temp(day: dt.date) -> float:
        return 3 if day < dt.date(2026, 3, 1) or day >= d(18) else 15

    return [WeatherDay(date=day, temp_max=temp(day), temp_min=0, rain_mm=0) for day in days(dt.date(2026, 1, 1), d(30))]


def analysis_inputs(*, with_orders: bool = True, events: list[Event] | None = None, past_festival: bool = True) -> AnalysisInputs:
    """평소 점심(9/1~11/17): 국수 3, 전 1. 지난 축제 날(10/24) 점심: 전 3, 국수 1."""
    sales = []
    if with_orders:
        for day in days(dt.date(2026, 9, 1), d(17)):
            sales.append(lunch(day, {"4": 3, "1": 1} if day == PAST_FESTIVAL else {"1": 3, "4": 1}))
    festival_before = Event(
        event_id="event_001", kind="LOCAL_FESTIVAL", title="지난 축제", distance_km=0.5,
        start_at=dt.datetime.combine(PAST_FESTIVAL, dt.time(11), tzinfo=SEOUL),
        end_at=dt.datetime.combine(PAST_FESTIVAL, dt.time(13), tzinfo=SEOUL),
    )
    return AnalysisInputs(
        store=ANALYSIS_STORE,
        orders=[order for order, _ in sales],
        order_items=[item for _, items in sales for item in items],
        menus=ORIGINAL,
        events=[*(PLAN.events if events is None else events), *([festival_before] if past_festival else [])],
        games=PLAN.games,
        weather=weather(),
    )


class FakeLookup:
    """세부 종류 → 정해 둔 후보. (매장, 세부 종류)별로 몇 번 불렸는지 센다."""

    def __init__(self, answers: dict[str, MenuCandidates] | None = None):
        self.answers = answers if answers is not None else {
            "WINTER": MenuCandidates(("5", "3"), WINTER_REASON),
            "NATIONAL_TEAM": MenuCandidates(("4",), ""),
            "LOCAL_FESTIVAL": MenuCandidates(("4", "3"), FESTIVAL_REASON),
        }
        self.calls: Counter = Counter()

    def __call__(self, store: dict, menus: list[Menu], kind: str) -> MenuCandidates:
        self.calls[(store["store_id"], kind)] += 1
        return self.answers.get(kind, EMPTY)


def with_effect(calendar, ref_id: str, effect: float):
    def changed(reason):
        return reason.model_copy(update={"effect": effect}) if reason.ref_id == ref_id else reason

    return [cell.model_copy(update={"reasons": [changed(r) for r in cell.reasons]}) for cell in calendar]


def with_reason(calendar, day: dt.date, reason: CalendarReason):
    return [cell.model_copy(update={"reasons": [*cell.reasons, reason]}) if cell.date == day else cell for cell in calendar]


def assemble(calendar=None, inputs=None, lookup=None, store_settings=None):
    calendar = PLAN.calendar if calendar is None else calendar
    store_settings = SETTINGS if store_settings is None else store_settings
    cards = plan_menu_orders(calendar, store_settings)
    lookup = lookup or FakeLookup()
    result = assemble_menu_board_cards(calendar, cards, inputs or analysis_inputs(), store_settings, STORE, ORIGINAL, lookup)
    return result, lookup


def card(result, day: int):
    return result[f"MENU_ORDER:2026-11-{day:02d}:2026-11-{day:02d}"]


def raised(result, day: int) -> tuple[str, ...]:
    return card(result, day).arrangement.raised


# ── 기간 ──


def test_tag_periods_cover_every_calendar_ref_id_with_this_years_season():
    periods = tag_periods_from_inputs(analysis_inputs(), PLAN.calendar)
    assert sorted(periods, key=lambda p: p.ref_id) == [
        TagPeriod("event_012", d(21), d(22)),  # 행사 시작~끝
        TagPeriod("game_031", d(19), d(19)),  # 경기 당일
        TagPeriod("season_winter", d(18), None),  # 달력 칸의 계절 근거 id 와 같은 값. 1~2월 겨울은 섞지 않는다. 아직 안 끝남
    ]



def test_restarted_season_keeps_only_the_first_period():
    # 한계(docstring): 11/18~11/25 겨울 → 사흘 따뜻함 → 11/29 다시 겨울이어도 season_winter 기간은 첫 기간 하나
    def temp(day: dt.date) -> float:
        return 15 if day < d(18) or d(26) <= day <= d(28) else 3

    inputs = analysis_inputs().model_copy(update={"weather": [WeatherDay(date=day, temp_max=temp(day), temp_min=0, rain_mm=0) for day in days(dt.date(2026, 3, 1), d(30))]})
    later = [cell.model_copy(update={"date": d(29), "reasons": [CalendarReason(tag="SEASON", ref_id="season_winter", effect=0.05)]}) for cell in PLAN.calendar if cell.date == d(23)]
    periods = tag_periods_from_inputs(inputs, [*PLAN.calendar, *later])
    assert TagPeriod("season_winter", d(18), d(25)) in periods


def test_event_ending_exactly_at_midnight_does_not_take_the_next_day():
    midnight = Event(
        event_id="event_012", kind="LOCAL_FESTIVAL", title="축제", distance_km=0.8,
        start_at=dt.datetime.combine(d(21), dt.time(11), tzinfo=SEOUL), end_at=dt.datetime.combine(d(22), dt.time(0), tzinfo=SEOUL),
    )
    periods = tag_periods_from_inputs(analysis_inputs(events=[midnight, *PLAN.events[1:]]), PLAN.calendar)
    assert TagPeriod("event_012", d(21), d(21)) in periods


def test_cards_without_store_settings_are_an_error():
    cards = plan_menu_orders(PLAN.calendar, SETTINGS)
    with pytest.raises(ValueError):
        assemble_menu_board_cards(PLAN.calendar, cards, analysis_inputs(), None, STORE, ORIGINAL, FakeLookup())


# ── 데모 주간 ──


def test_demo_week_cards():
    result, lookup = assemble()
    assert sorted(result) == [f"MENU_ORDER:2026-11-{day}:2026-11-{day}" for day in (18, 19, 20, 21, 23)]
    assert raised(result, 18) == ("5", "3")  # 겨울: 지난 겨울 판매 기록이 없어 LLM 만
    assert card(result, 18).reason == WINTER_REASON
    assert raised(result, 19) == ("4",)  # 경기: LLM 이유가 비어 기존 카드 문구
    assert card(result, 19).reason == "경기 때문에 메뉴판 순서를 바꿔요."
    assert raised(result, 20) == ("5", "3")
    assert raised(result, 21) == ("4", "3")  # 축제: LLM + 지난 축제 날 데이터(전 +50%p)
    assert card(result, 21).reason == FESTIVAL_REASON
    # 23일은 축제가 끝나도 겨울 배치다(원래 순서로 되돌리기가 아니다)
    assert card(result, 23).basis == "season_winter"
    assert raised(result, 23) == ("5", "3")
    assert card(result, 23).reason == WINTER_REASON
    assert not any(c.unchanged for c in result.values())
    # 날짜마다 다시 계산하지 않는다: 세부 종류마다 LLM 조회는 한 번
    assert lookup.calls == Counter({("store_001", "WINTER"): 1, ("store_001", "NATIONAL_TEAM"): 1, ("store_001", "LOCAL_FESTIVAL"): 1})


def test_kind_without_sales_history_uses_llm_only():
    # 평소 판매 기록은 있지만 지난 축제가 없으면 축제(LOCAL_FESTIVAL)의 n = 0 → LLM 점수만
    lookup = FakeLookup({"LOCAL_FESTIVAL": MenuCandidates(("3",), FESTIVAL_REASON)})
    with_history, _ = assemble(lookup=lookup)
    without_history, _ = assemble(inputs=analysis_inputs(past_festival=False), lookup=FakeLookup(lookup.answers))
    assert raised(with_history, 21) == ("3", "4")  # 지난 축제 데이터(전 +50%p)가 전을 함께 올린다
    assert raised(without_history, 21) == ("3",)  # 데이터가 없으면 LLM 후보만


def test_store_without_any_orders_uses_llm_only():
    result, _ = assemble(inputs=analysis_inputs(with_orders=False))
    assert raised(result, 18) == ("5", "3")
    assert raised(result, 21) == ("4", "3")


def test_llm_ids_not_in_the_menu_are_ignored():
    lookup = FakeLookup({"WINTER": MenuCandidates(("99", "5"), WINTER_REASON)})
    result, _ = assemble(lookup=lookup)
    assert raised(result, 18) == ("5",)


def test_day_after_closed_day_compares_with_the_open_day_before():
    closed_saturday = SETTINGS.model_copy(update={"closed_weekdays": ["SAT"]})  # 11/21(토) 휴무
    calendar = [cell for cell in PLAN.calendar if cell.date != d(21)]
    inputs = analysis_inputs().model_copy(update={"store": ANALYSIS_STORE.model_copy(update={"closed_weekdays": ["SAT"]})})
    result, _ = assemble(calendar=calendar, inputs=inputs, store_settings=closed_saturday)
    assert sorted(result) == [f"MENU_ORDER:2026-11-{day}:2026-11-{day}" for day in (18, 19, 20, 22, 23)]
    assert raised(result, 22) == ("4", "3")  # 직전 영업일 11/20(겨울)과 견주어 바뀐다
    assert card(result, 22).unchanged is False


def test_switching_to_another_festival_of_the_same_kind_changes_nothing():
    second = Event(
        event_id="event_013", kind="LOCAL_FESTIVAL", title="다른 축제", distance_km=0.6,
        start_at=dt.datetime.combine(d(22), dt.time(11), tzinfo=SEOUL), end_at=dt.datetime.combine(d(22), dt.time(18), tzinfo=SEOUL),
    )
    first = PLAN.events[0].model_copy(update={"end_at": dt.datetime.combine(d(21), dt.time(18), tzinfo=SEOUL)})
    calendar = [
        cell.model_copy(update={"reasons": [r.model_copy(update={"ref_id": "event_013"}) if r.ref_id == "event_012" else r for r in cell.reasons]})
        if cell.date == d(22) else cell
        for cell in PLAN.calendar
    ]
    result, lookup = assemble(calendar=calendar, inputs=analysis_inputs(events=[first, second]))
    assert card(result, 22).basis == "event_013"
    assert card(result, 22).unchanged is True  # 근거 id 는 바뀌었지만 같은 종류라 배치가 같다
    assert card(result, 22).reason == UNCHANGED_REASON  # LLM 이유보다 먼저
    assert lookup.calls[("store_001", "LOCAL_FESTIVAL")] == 1


def test_festival_filtered_by_benefit_changes_nothing():
    calendar = with_effect(PLAN.calendar, "event_012", 0.08)  # 0.08 × 2일 < 0.2
    result, lookup = assemble(calendar=calendar)
    assert card(result, 21).unchanged is True and card(result, 23).unchanged is True
    assert card(result, 21).reason == card(result, 23).reason == UNCHANGED_REASON == "메뉴판은 지금 순서 그대로 두면 돼요."
    assert raised(result, 21) == raised(result, 23) == ("5", "3")  # 계속 겨울 배치
    assert lookup.calls[("store_001", "LOCAL_FESTIVAL")] == 0


def test_change_back_to_original_order_after_festival_is_not_unchanged():
    # 겨울 후보가 없고 지난 겨울 기록도 없으면 겨울 배치는 원래 순서(점수 모두 0)
    lookup = FakeLookup({"LOCAL_FESTIVAL": MenuCandidates(("4", "3"), FESTIVAL_REASON), "NATIONAL_TEAM": MenuCandidates(("4",), "")})
    result, _ = assemble(lookup=lookup)
    assert card(result, 23).arrangement.same_as_original is True
    assert card(result, 23).unchanged is False  # 어제는 축제 배치였으니 오늘 원래 순서로 바뀐다
    assert card(result, 23).reason == BACK_TO_ORIGINAL_REASON == "추천할 메뉴를 찾지 못해 원래 순서로 돌려요."
    assert card(result, 18).unchanged is True  # 어제도 원래 순서, 오늘도 원래 순서
    assert card(result, 18).reason == UNCHANGED_REASON


def test_reason_follows_the_basis_when_llm_reason_is_empty():
    lookup = FakeLookup({"WINTER": MenuCandidates(("5", "3"), ""), "NATIONAL_TEAM": MenuCandidates(("4",), "")})
    result, _ = assemble(lookup=lookup)
    assert card(result, 18).reason == "계절 변화 때문에 메뉴판 순서를 바꿔요."
    # 경기가 끝나 겨울 배치로 바뀌는 날: 엔진 문구("경기 기간이 끝나 … 되돌려요")가 아니라 기준 태그(겨울) 문구
    assert card(result, 20).reason == "계절 변화 때문에 메뉴판 순서를 바꿔요."
    assert card(result, 19).reason == "경기 때문에 메뉴판 순서를 바꿔요."


def test_reason_for_going_back_to_original_order_names_the_tag_that_ended():
    no_season = [cell.model_copy(update={"reasons": [r for r in cell.reasons if r.tag != "SEASON"]}) for cell in PLAN.calendar]
    result, _ = assemble(calendar=no_season)
    assert card(result, 20).basis is None
    assert card(result, 20).reason == "경기 기간이 끝나 메뉴판 순서를 되돌려요."
    assert card(result, 23).reason == "근처 행사 기간이 끝나 메뉴판 순서를 되돌려요."


def test_unknown_ref_id_is_dropped_before_choosing_the_basis(caplog):
    unknown = CalendarReason(tag="EVENT", ref_id="event_099", effect=0.5)  # inputs.events 에 없는 행사. 교체 이득이 부담을 넘는 크기
    calendar = with_reason(PLAN.calendar, d(20), unknown)
    with caplog.at_level(logging.WARNING):
        result, _ = assemble(calendar=calendar)
    assert "event_099" in caplog.text
    assert card(result, 20).basis == "season_winter"  # 모르는 행사를 빼면 그날 남는 겨울이 기준 태그
    assert raised(result, 20) == ("5", "3")
    assert card(result, 20).reason != NO_PICK_REASON


def test_share_change_is_computed_once_per_basis(monkeypatch):
    from app.menu_board import assemble as module

    calls = Counter()

    def counting(inputs, tag, kind, as_of):
        calls[(kind, as_of)] += 1
        return real(inputs, tag, kind, as_of)

    real = module.menu_share_lift
    monkeypatch.setattr(module, "menu_share_lift", counting)
    assemble()
    assert calls == Counter({("WINTER", d(18)): 1, ("NATIONAL_TEAM", d(19)): 1, ("LOCAL_FESTIVAL", d(21)): 1})  # 기준일은 기간 첫날


def test_data_score_uses_only_days_before_the_basis_period_started():
    # 축제 이틀 동안 국수만 팔렸다. 기준일(축제 첫날 11/21) 앞선 날만 쓰므로 지난 축제(10/24, 전 +50%p)만 본다.
    # 진행 중인 축제 날까지 섞으면 전 (+50 − 25 − 25) / 3 = 0 이 되어 올릴 메뉴가 없다
    inputs = analysis_inputs()
    extra = [lunch(day, {"1": 9}) for day in (d(21), d(22))]
    inputs = inputs.model_copy(update={
        "orders": [*inputs.orders, *(order for order, _ in extra)],
        "order_items": [*inputs.order_items, *(item for _, items in extra for item in items)],
    })
    lookup = FakeLookup({"WINTER": MenuCandidates(("5", "3"), WINTER_REASON)})  # 축제 LLM 후보 없음: 데이터만
    result, _ = assemble(inputs=inputs, lookup=lookup)
    assert raised(result, 21) == ("4",)


# ── 실제 목업 DB ──


@pytest.fixture(scope="module")
def no_clova():
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(settings, "sentence_polish_enabled", False)
        patch.setattr(settings, "clova_studio_api_key", "")
        store_snapshot_cache.clear_all()
        yield
        store_snapshot_cache.clear_all()


@pytest.mark.parametrize(
    ("store_id", "now"),
    [
        ("s001", dt.datetime(2026, 11, 17, 13, 50, tzinfo=SEOUL)),
        ("s003", dt.datetime(2026, 12, 8, 10, 35, tzinfo=SEOUL)),
    ],
)
def test_mock_store_cards_have_periods_and_valid_shape(no_clova, store_id, now):
    # 목업 DB 의 특정 날짜·태그·값은 단정하지 않는다. 카드가 있으면 모양과 규칙만 본다
    snapshot = store_snapshot_cache.get_snapshot(store_id, now)
    calendar = store_snapshot_cache.calendar_for_planner(store_id, snapshot.inputs, snapshot.calendar_cells, now)
    seen = {r.ref_id for cell in calendar for r in cell.reasons if r.tag != "WEATHER"}
    period_ids = {period.ref_id for period in tag_periods_from_inputs(snapshot.inputs, calendar)}
    assert seen <= period_ids
    cards = [item for item in snapshot.plan.plan_items if item.task_type == "MENU_ORDER"]
    store = {"store_id": store_id, "name": snapshot.store["name"], "category": snapshot.store["category"]}
    original = original_menu_order(store_id)
    menu_ids = [menu.menu_id for menu in original]
    result = assemble_menu_board_cards(calendar, cards, snapshot.inputs, snapshot.settings, store, original, FakeLookup({}))
    assert set(result) == {item.plan_id for item in cards}
    for plan_id, board in result.items():
        assert board.plan_id == plan_id
        assert board.basis is None or board.basis in period_ids
        order = [menu.menu_id for menu in board.arrangement.order]
        assert sorted(order) == sorted(menu_ids)  # 그 매장 메뉴를 빠짐없이, 겹치지 않게
        raised = list(board.arrangement.raised)
        assert set(raised) <= set(menu_ids)
        assert len(raised) <= min(2, len(menu_ids))
        assert order[: len(raised)] == raised  # 올린 메뉴가 맨 위
        assert isinstance(board.reason, str)
        assert isinstance(board.unchanged, bool)
        if board.unchanged:
            assert board.reason == UNCHANGED_REASON


def test_overnight_store_without_cards_gets_nothing(no_clova):
    now = dt.datetime(2026, 11, 17, 13, 50, tzinfo=SEOUL)
    snapshot = store_snapshot_cache.get_snapshot("s002", now)
    assert snapshot.plan is None  # 계획 엔진이 자정 넘김 매장의 카드를 만들지 않는다
    calendar = store_snapshot_cache.calendar_for_planner("s002", snapshot.inputs, snapshot.calendar_cells, now)
    store = {"store_id": "s002", "name": snapshot.store["name"], "category": snapshot.store["category"]}
    lookup = FakeLookup()
    assert assemble_menu_board_cards(calendar, [], snapshot.inputs, snapshot.settings, store, original_menu_order("s002"), lookup) == {}
    assert not lookup.calls
