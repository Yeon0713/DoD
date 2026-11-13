"""점심·저녁·밤 시간대(15시·20시 경계)에서 달라지는 규칙.

앱은 매장 시간대를 점심(오픈~15시)·저녁(15~20시)·밤(20시~마감)으로 넘긴다. 기본 경계(MORNING~11·LUNCH~17·DINNER)와
결과가 달라지는 규칙만 작은 합성 데이터로 손계산해 확인한다. 기대값은 아래 주석의 계산으로 정했다.
"""

import datetime as dt

from app.analysis.input_shapes import AnalysisInputs, DaypartRange, Order, StoreInfo
from app.analysis.pattern.baseline import build_baselines
from app.analysis.pattern.sales_daily import build_sales_daily
from app.analysis.special_cells import cell_keys, find_special_cells
from app.core.seoul_time import SEOUL
from app.planner.data_shapes import Event, Game

# 10:00~22:00 매장. 시간대는 [시작, 끝) 이다.
LUNCH_DINNER_NIGHT = [
    DaypartRange(daypart="LUNCH", start=dt.time(10), end=dt.time(15)),
    DaypartRange(daypart="DINNER", start=dt.time(15), end=dt.time(20)),
    DaypartRange(daypart="NIGHT", start=dt.time(20), end=dt.time(22)),
]
STORE = StoreInfo(
    store_id="s1", name="테스트", lat=0, lng=0, open_time=dt.time(10), close_time=dt.time(22), dayparts=LUNCH_DINNER_NIGHT
)
DEFAULT_STORE = STORE.model_copy(update={"dayparts": None})  # MORNING 10~11, LUNCH 11~17, DINNER 17~22
DAY = dt.date(2026, 11, 2)  # 월요일


def at(day: dt.date, hour: int, minute: int = 0) -> dt.datetime:
    return dt.datetime(day.year, day.month, day.day, hour, minute, tzinfo=SEOUL)


def game_dayparts(store: StoreInfo, hour: int, minute: int = 0) -> list[str]:
    inputs = AnalysisInputs(store=store, games=[Game(game_id="game_001", kind="BASEBALL", title="경기", start_at=at(DAY, hour, minute))])
    return [c.daypart for c in find_special_cells(inputs, DAY, DAY)]


# ── 경기: 시작 시간대 + 그다음 시간대 ──


def test_game_at_1830_marks_dinner_and_night():
    # 18:30 은 저녁(15~20)에 속한다. 그다음은 밤(20~22) → 저녁·밤 두 칸
    assert game_dayparts(STORE, 18, 30) == ["DINNER", "NIGHT"]
    # 기본 경계에서는 18:30 이 DINNER(17~22)이고 그 뒤 시간대가 없다 → DINNER 한 칸
    assert game_dayparts(DEFAULT_STORE, 18, 30) == ["DINNER"]


def test_game_at_exactly_2000_marks_night_only():
    # 20:00 은 저녁의 끝(20:00, 포함 안 함)이자 밤의 시작(20:00, 포함) → 밤. 밤이 마지막 시간대라 다음 칸이 없다
    assert game_dayparts(STORE, 20) == ["NIGHT"]
    # 19:59 는 아직 저녁 → 저녁·밤
    assert game_dayparts(STORE, 19, 59) == ["DINNER", "NIGHT"]


def test_game_at_1430_marks_lunch_and_dinner():
    # 14:30 은 점심(10~15) → 점심과 그다음 저녁
    assert game_dayparts(STORE, 14, 30) == ["LUNCH", "DINNER"]
    # 기본 경계에서는 14:30 이 LUNCH(11~17) → LUNCH·DINNER (같은 이름이지만 칸의 시간 범위가 다르다)
    assert game_dayparts(DEFAULT_STORE, 14, 30) == ["LUNCH", "DINNER"]


def test_game_at_closing_time_is_not_marked():
    # 22:00 은 밤의 끝(포함 안 함)이라 어느 시간대에도 없다 → 표시하지 않는다
    assert game_dayparts(STORE, 22) == []


# ── 행사: 시간대와 겹친 시간이 0보다 클 때만 ──


def test_event_ending_at_2000_does_not_touch_night():
    # 행사 13:00~20:00, 0.5km.
    #   점심 10~15 와 겹침 13:00~15:00 = 120분 → 표시
    #   저녁 15~20 와 겹침 15:00~20:00 = 300분 → 표시
    #   밤 20~22 와 겹침 20:00~20:00 = 0분 → 표시 안 함
    event = Event(event_id="event_001", kind="LOCAL_FESTIVAL", title="행사", start_at=at(DAY, 13), end_at=at(DAY, 20), distance_km=0.5)
    found = find_special_cells(AnalysisInputs(store=STORE, events=[event]), DAY, DAY)
    assert [c.daypart for c in found] == ["LUNCH", "DINNER"]


# ── 매출: 주문 시각으로 시간대 칸에 넣는다 ──


def test_orders_on_15_and_20_boundaries_go_to_the_later_daypart():
    # 주문 시각 → 칸
    #   14:59 10,000 → 점심            점심 = 10,000
    #   15:00 20,000 → 저녁 (경계 포함)
    #   19:59 30,000 → 저녁            저녁 = 20,000 + 30,000 = 50,000
    #   20:00 40,000 → 밤 (경계 포함)
    #   21:59 50,000 → 밤              밤 = 40,000 + 50,000 = 90,000
    #   22:00 60,000 → 마감(22:00, 포함 안 함)이라 칸 밖 → 영업시간 밖 1건
    times = [(14, 59, 10_000), (15, 0, 20_000), (19, 59, 30_000), (20, 0, 40_000), (21, 59, 50_000), (22, 0, 60_000)]
    orders = [
        Order(order_id=str(i), ordered_at=at(DAY, h, m), channel="HALL", total_amount=amount) for i, (h, m, amount) in enumerate(times)
    ]
    result = build_sales_daily(AnalysisInputs(store=STORE, orders=orders), at(DAY, 22, 30))

    assert {r.daypart: r.sales_amount for r in result.rows} == {"LUNCH": 10_000, "DINNER": 50_000, "NIGHT": 90_000}
    assert result.outside_order_count == 1


# ── 밤 시간대 기준선 ──


def test_night_baseline_drops_the_night_after_a_dinner_game():
    # 월요일마다 20:30(밤) 주문 하나. 기준일 11/16(월)의 기준선은 직전 8주(9/21~11/9) 월요일 밤 칸의 중앙값이다.
    #   9/28 110,000 / 10/5 130,000 / 10/12 100,000 / 10/19 120,000 / 10/26 300,000 / 11/2 140,000 / 11/9 160,000
    #   (9/21 은 주문이 없고, 첫 주문 날 9/28 전이라 칸이 없다)
    # 10/26 19:00 에 경기 → 시작 시간대 저녁 + 다음 시간대 밤이 특별한 칸 → 10/26 밤(300,000)은 뺀다
    #   남은 6주 정렬: 100,000 110,000 120,000 130,000 140,000 160,000
    #   짝수 개라 가운데 두 값의 평균: (120,000 + 130,000) / 2 = 125,000
    # (경기 칸을 빼지 않았다면 7개의 가운데 130,000. 기본 경계였다면 19:00 경기는 DINNER 만 표시하므로 밤 칸이 따로 없다)
    nights = {
        dt.date(2026, 9, 28): 110_000,
        dt.date(2026, 10, 5): 130_000,
        dt.date(2026, 10, 12): 100_000,
        dt.date(2026, 10, 19): 120_000,
        dt.date(2026, 10, 26): 300_000,
        dt.date(2026, 11, 2): 140_000,
        dt.date(2026, 11, 9): 160_000,
    }
    orders = [
        Order(order_id=str(i), ordered_at=at(day, 20, 30), channel="HALL", total_amount=amount)
        for i, (day, amount) in enumerate(nights.items())
    ]
    game = Game(game_id="game_001", kind="NATIONAL_TEAM", title="국가대표 경기", start_at=at(dt.date(2026, 10, 26), 19))
    inputs = AnalysisInputs(store=STORE, orders=orders, games=[game])
    as_of = dt.date(2026, 11, 16)

    rows = build_sales_daily(inputs, at(as_of, 9)).rows
    excluded = cell_keys(find_special_cells(inputs, rows[0].date, as_of - dt.timedelta(days=1)))
    assert excluded == {(dt.date(2026, 10, 26), "DINNER"), (dt.date(2026, 10, 26), "NIGHT")}

    result = build_baselines(rows, excluded, as_of, ["LUNCH", "DINNER", "NIGHT"])
    assert len(result) == 7 * 3
    assert result[("MON", "NIGHT")] == 125_000
    # 월요일 저녁은 7주 모두 0원, 10/26 저녁을 빼도 6주가 0원 → 0
    assert result[("MON", "DINNER")] == 0
