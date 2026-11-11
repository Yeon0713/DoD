"""특별한 칸 (app/analysis/special_cells.py).

특별한 칸은 원본 조건(행사·경기·날씨)에 걸리는 칸이다. 과거 효과가 작아 태그가 붙지 않는 칸도 포함한다.
"""

import datetime as dt

import pytest

from app.analysis.input_shapes import AnalysisInputs, StoreInfo, WeatherDay
from app.analysis.mock_csv_reader import MOCK_DIR, read_mock_csv
from app.analysis.special_cells import cell_keys, find_special_cells
from app.core.seoul_time import SEOUL
from app.planner.data_shapes import Event, Game

STORE = StoreInfo(store_id="s1", name="테스트", lat=0, lng=0, open_time=dt.time(10), close_time=dt.time(22))
DAY = dt.date(2026, 11, 2)  # 월요일


def at(hour: int, minute: int = 0, day: dt.date = DAY) -> dt.datetime:
    return dt.datetime(day.year, day.month, day.day, hour, minute, tzinfo=SEOUL)


def cells(inputs: AnalysisInputs, start: dt.date = DAY, end: dt.date = DAY + dt.timedelta(6)) -> set[tuple]:
    return {(c.date, c.daypart, c.tag, c.ref_id) for c in find_special_cells(inputs, start, end)}


def event(event_id: str, start: dt.datetime, end: dt.datetime, km: float) -> Event:
    return Event(event_id=event_id, kind="LOCAL_FESTIVAL", title="축제", start_at=start, end_at=end, distance_km=km)


def test_event_within_2km_marks_overlapping_cells_each_day():
    inputs = AnalysisInputs(
        store=STORE,
        events=[
            event("event_001", at(12), at(20, day=DAY + dt.timedelta(1)), 2.0),  # 2km 와 같으면 포함, 이틀
            event("event_002", at(10, day=DAY + dt.timedelta(3)), at(11, day=DAY + dt.timedelta(3)), 0.5),  # 11:00 에 끝나면 점심과는 안 겹친다
            event("event_003", at(12), at(13), 2.1),  # 2km 넘음
        ],
    )
    tue = DAY + dt.timedelta(1)
    thu = DAY + dt.timedelta(3)
    assert cells(inputs) == {
        (DAY, "LUNCH", "EVENT", "event_001"),
        (DAY, "DINNER", "EVENT", "event_001"),
        (tue, "MORNING", "EVENT", "event_001"),
        (tue, "LUNCH", "EVENT", "event_001"),
        (tue, "DINNER", "EVENT", "event_001"),
        (thu, "MORNING", "EVENT", "event_002"),
    }


def game(game_id: str, start: dt.datetime) -> Game:
    return Game(game_id=game_id, kind="BASEBALL", title="야구", start_at=start)


def test_game_marks_start_daypart_and_the_next_one():
    tue, wed = DAY + dt.timedelta(1), DAY + dt.timedelta(2)
    inputs = AnalysisInputs(
        store=STORE,
        games=[
            game("game_001", at(10, 30)),  # 아침 시작 → 아침·점심
            game("game_002", at(14, day=tue)),  # 점심 시작 → 점심·저녁
            game("game_003", at(18, 30, day=wed)),  # 저녁 시작 → 저녁만
            game("game_004", at(8, day=wed)),  # 오픈 전 시작 → 표시하지 않는다
            game("game_005", at(22, 30, day=wed)),  # 마감 뒤 시작 → 표시하지 않는다
        ],
    )
    assert cells(inputs) == {
        (DAY, "MORNING", "GAME", "game_001"),
        (DAY, "LUNCH", "GAME", "game_001"),
        (tue, "LUNCH", "GAME", "game_002"),
        (tue, "DINNER", "GAME", "game_002"),
        (wed, "DINNER", "GAME", "game_003"),
    }


def test_weather_marks_every_cell_of_the_day_at_the_thresholds():
    days = [DAY + dt.timedelta(n) for n in range(5)]
    inputs = AnalysisInputs(
        store=STORE,
        weather=[
            WeatherDay(date=days[0], temp_max=20, temp_min=10, rain_mm=5.0),  # 비 5mm 와 같으면 포함
            WeatherDay(date=days[1], temp_max=20, temp_min=10, rain_mm=4.9),  # 비 5mm 미만 → 아님
            WeatherDay(date=days[2], temp_max=33.0, temp_min=25, rain_mm=0),  # 폭염
            WeatherDay(date=days[3], temp_max=-3, temp_min=-12.0, rain_mm=6),  # 한파와 비가 같은 날
            WeatherDay(date=days[4], temp_max=32.9, temp_min=-11.9, rain_mm=0),  # 아무것도 아님
        ],
    )
    expected = {
        *((days[0], p, "WEATHER", "weather:2026-11-02:RAIN") for p in ("MORNING", "LUNCH", "DINNER")),
        *((days[2], p, "WEATHER", "weather:2026-11-04:HEAT") for p in ("MORNING", "LUNCH", "DINNER")),
        *((days[3], p, "WEATHER", "weather:2026-11-05:RAIN") for p in ("MORNING", "LUNCH", "DINNER")),
        *((days[3], p, "WEATHER", "weather:2026-11-05:COLD") for p in ("MORNING", "LUNCH", "DINNER")),
    }
    assert cells(inputs) == expected


def test_days_outside_the_range_and_closed_days_are_left_out():
    store = STORE.model_copy(update={"closed_weekdays": ["TUE"]})
    rainy = [WeatherDay(date=DAY + dt.timedelta(n), temp_max=20, temp_min=10, rain_mm=10) for n in range(-1, 4)]
    inputs = AnalysisInputs(store=store, weather=rainy)
    found = cells(inputs, start=DAY, end=DAY + dt.timedelta(2))
    assert {day for day, *_ in found} == {DAY, DAY + dt.timedelta(2)}  # 전날·화요일(휴무)·범위 뒤는 없다


# 9/23~11/17 사이 목업의 특별한 칸. 원본 행사·경기·날씨 CSV를 보고 손으로 정했다.
ALL = ("MORNING", "LUNCH", "DINNER")
MOCK_SPECIAL_BY_HAND = {
    *((dt.date(2026, 9, d), p) for d in (23, 24, 25) for p in ALL),  # 강원대 대동제 0.5km, 9/23 10시~9/25 23시
    *((dt.date(2026, 10, d), p) for d in (10, 11) for p in ALL),  # 지역 축제 1.6km, 10/10 10시~10/11 21시
    (dt.date(2026, 9, 30), "DINNER"),  # 야구 18:30
    (dt.date(2026, 10, 14), "DINNER"),  # 국가대표 축구 20:00
    (dt.date(2026, 10, 20), "DINNER"),  # 야구 18:30
    (dt.date(2026, 10, 28), "DINNER"),  # 야구 18:30
    *((dt.date(2026, m, d), p) for m, d in ((10, 8), (10, 27), (11, 5), (11, 6), (11, 8)) for p in ALL),  # 비 5mm 이상
}


@pytest.mark.skipif(not (MOCK_DIR / "orders.csv").exists(), reason="목업 CSV 가 없다")
def test_mock_special_cells_match_hand_picked_cells():
    found = find_special_cells(read_mock_csv(), dt.date(2026, 9, 23), dt.date(2026, 11, 17))
    assert cell_keys(found) == MOCK_SPECIAL_BY_HAND
