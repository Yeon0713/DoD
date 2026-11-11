"""계절 (app/analysis/store_calendar/season.py).

계절은 최고기온이 며칠 이어서 한쪽으로 넘어가 있는 기간(여름·겨울)이다. 그 사이에는 계절이 없다.
3일 연속 조건을 채우면 그 3일 중 첫날부터 시작하고, 반대 조건 3일 연속의 첫날부터 끝난다.
"""

import datetime as dt

import pytest

from app.analysis.input_shapes import WeatherDay
from app.analysis.mock_csv_reader import MOCK_DIR, read_mock_csv
from app.analysis.store_calendar.season import Season, season_ref_id, seasons_between

D1 = dt.date(2026, 11, 1)


def day(n: int) -> dt.date:
    return D1 + dt.timedelta(days=n)


def weather(*temp_max: float, first: int = 0) -> list[WeatherDay]:
    """first 번째 날부터 하루씩 최고기온."""
    return [WeatherDay(date=day(first + i), temp_max=t, temp_min=t - 8, rain_mm=0) for i, t in enumerate(temp_max)]


def seasons(w: list[WeatherDay], last: int) -> list[Season | None]:
    result = seasons_between(w, day(0), day(last))
    return [result[day(n)] for n in range(last + 1)]


def test_winter_starts_on_the_first_of_three_days_below_10():
    w = weather(12, 9.9, 9, 11, 9, 8, 7)  # 날짜 0~6. 1~2일은 이틀뿐이라 아니다. 4~6일이 3일 연속
    assert seasons(w, 6) == [None, None, None, None, "WINTER", "WINTER", "WINTER"]


def test_winter_ends_on_the_first_of_three_days_at_10_or_above():
    w = weather(8, 7, 6, 12, 11, 9, 13, 14, 15)  # 날짜 0~8. 3~4일은 이틀만 10도 이상, 6~8일이 3일 연속
    assert seasons(w, 8) == ["WINTER"] * 6 + [None, None, None]


def test_summer_starts_above_25_and_ends_at_25_or_below():
    w = weather(25.5, 26, 27, 24, 23, 22, 30)
    assert seasons(w, 6) == ["SUMMER", "SUMMER", "SUMMER", None, None, None, None]


def test_summer_can_turn_straight_into_winter():
    w = weather(30, 29, 28, 9, 8, 7)
    assert seasons(w, 5) == ["SUMMER"] * 3 + ["WINTER"] * 3


def test_winter_can_turn_straight_into_summer():
    w = weather(5, 6, 7, 26, 27, 28)
    assert seasons(w, 5) == ["WINTER"] * 3 + ["SUMMER"] * 3


def test_weather_in_any_order_gives_the_same_seasons():
    w = weather(12, 9, 8, 7, 11)
    assert seasons(list(reversed(w)), 4) == seasons(w, 4) == [None, "WINTER", "WINTER", "WINTER", "WINTER"]


def test_season_ref_id():
    assert season_ref_id("WINTER") == "season_winter"
    assert season_ref_id("SUMMER") == "season_summer"


def test_exactly_10_and_25_degrees_belong_to_the_ending_side():
    assert seasons(weather(10, 10, 10), 2) == [None, None, None]  # 10도는 "미만"이 아니다
    assert seasons(weather(9, 9, 9, 10, 10, 10), 5) == ["WINTER"] * 3 + [None] * 3  # 10도는 겨울을 끝낸다
    assert seasons(weather(25, 25, 25), 2) == [None, None, None]  # 25도는 "초과"가 아니다
    assert seasons(weather(26, 26, 26, 25, 25, 25), 5) == ["SUMMER"] * 3 + [None] * 3  # 25도는 여름을 끝낸다


def test_the_last_season_carries_on_after_the_weather_record_ends():
    assert seasons(weather(9, 8, 7), 6) == ["WINTER"] * 7  # 3~6일은 기록이 없다


def test_a_missing_day_breaks_the_three_day_run():
    w = weather(9, 8) + weather(7, 6, first=3)  # 2일 기록이 없다
    assert seasons(w, 4) == [None] * 5
    w = weather(9, 8, 7, 12) + weather(13, 14, first=5)  # 겨울 중 4일이 빠져 3·5·6일은 이어지지 않는다
    assert seasons(w, 6) == ["WINTER"] * 7



def test_when_a_date_appears_twice_the_later_record_is_used():
    """같은 날짜가 여러 번 오면 나중 값만 쓴다. 날짜가 겹쳐도 빠진 날은 빠진 날이다."""
    w = [WeatherDay(date=day(n), temp_max=t, temp_min=0, rain_mm=0) for n, t in [(0, 9), (2, 9), (2, 8)]]
    assert seasons(w, 2) == [None, None, None]  # 1일이 빠졌다
    w = [WeatherDay(date=day(n), temp_max=t, temp_min=0, rain_mm=0) for n, t in [(0, 9), (1, 9), (1, 8), (2, 7)]]
    assert seasons(w, 2) == ["WINTER"] * 3  # 0·1·2일 연속
    w = [WeatherDay(date=day(n), temp_max=t, temp_min=0, rain_mm=0) for n, t in [(0, 9), (1, 9), (2, 9), (2, 12)]]
    assert seasons(w, 2) == [None, None, None]  # 2일은 나중 값 12도를 쓴다

# ── 목업 데이터: 원본 weather_daily.csv 를 손으로 훑은 결과와 비교 ──


@pytest.mark.skipif(not (MOCK_DIR / "orders.csv").exists(), reason="목업 CSV 가 없다")
def test_mock_seasons_match_hand_calculation():
    result = seasons_between(read_mock_csv().weather, dt.date(2026, 8, 17), dt.date(2026, 12, 21))

    assert result[dt.date(2026, 8, 17)] == "SUMMER"  # 8/17~19: 33.3·30.9·32.6도
    assert result[dt.date(2026, 9, 14)] == "SUMMER"
    assert result[dt.date(2026, 9, 15)] is None  # 9/15~17: 24.1·24.6·22.6도
    assert {result[dt.date(2026, 11, d)] for d in range(17, 22)} == {None}  # 데모 주 앞부분은 계절 없음
    assert result[dt.date(2026, 11, 22)] == "WINTER"  # 11/22~24: 9.4·9.9·7.9도
    assert {result[dt.date(2026, 12, d)] for d in range(1, 22)} == {"WINTER"}  # 날씨 기록은 11/30까지, 그 뒤는 이어 간다
