"""좌표 → 격자, 관측소 고르기, 발표 시각 계산."""

import datetime as dt

import pytest

from app.core.seoul_time import SEOUL
from app.weather.coordinates import distance_km, to_grid
from app.weather.parsing import issue_times
from app.weather.short_forecast import BASE_HOURS
from app.weather.stations import nearest_stations, parse_stations
from kma_samples import STATIONS_TEXT


@pytest.mark.parametrize(
    ("lat", "lng", "grid"),
    [
        (37.5665, 126.9780, (60, 127)),  # 서울 시청 (단기예보 활용가이드 격자표 서울 60,127)
        (37.8813, 127.7298, (73, 134)),  # 춘천
        (33.4996, 126.5312, (53, 38)),  # 제주
    ],
)
def test_to_grid_matches_kma_grid(lat, lng, grid):
    assert to_grid(lat, lng) == grid


def test_distance_km_is_great_circle():
    assert distance_km(37.5665, 126.9780, 37.5665, 126.9780) == 0
    assert distance_km(37.5665, 126.9780, 37.8813, 127.7298) == pytest.approx(74.0, abs=2)  # 서울-춘천 약 74km


def test_nearest_stations_reads_official_list_and_sorts_by_distance():
    stations = parse_stations(STATIONS_TEXT)
    assert [s.station_id for s in stations] == [101, 108, 211]  # 잘린 줄은 버린다
    assert stations[0].name == "춘천"  # 주소에 빈칸이 있어도 칸이 밀리지 않는다
    near = nearest_stations(stations, 37.8813, 127.7298)
    assert [s.station_id for s in near] == [101, 211, 108]
    assert near[0].name == "춘천" and near[0].distance_km < 3


def _at(day, hh, mm=0):
    return dt.datetime(2026, 11, day, hh, mm, tzinfo=SEOUL)


def test_short_forecast_issue_times_wait_ten_minutes_after_issue():
    assert issue_times(_at(13, 2, 9), BASE_HOURS, dt.timedelta(minutes=10), 2) == [_at(12, 23), _at(12, 20)]
    assert issue_times(_at(13, 2, 10), BASE_HOURS, dt.timedelta(minutes=10), 2) == [_at(13, 2), _at(12, 23)]
    assert issue_times(_at(13, 14, 5), BASE_HOURS, dt.timedelta(minutes=10), 1) == [_at(13, 11)]
