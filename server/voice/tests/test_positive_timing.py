"""P: 좋은 리뷰 답글 올리는 때 (donna-voice/docs/test-scenarios-closed-loop.md P).

평일(월~목) 리뷰는 그 주 토요일 주말 첫 식사 피크 한 시간 전(10:30 ~ 11:30 안), 주말(금~일) 리뷰는 24 ~ 48시간 안의
다음 식사 피크 한 시간 전. 날씨·행사·경기는 시각을 바꾸지 않고 글에만 들어간다.
"""

import datetime as dt

import pytest

from app.core.seoul_time import SEOUL
from voice.jobs import schedule

CHOONGJANG = {"open_time": "10:30", "close_time": "20:30", "closed_weekdays": [], "peak_hours": {"lunch": "12:00", "dinner": "17:00"},
              "rain_menu": "옹심이"}
PLAIN = {"open_time": "10:00", "close_time": "22:00", "closed_weekdays": []}  # 피크 정보가 없는 가게
TUESDAY_0902 = dt.datetime(2026, 11, 17, 9, 2, tzinfo=SEOUL)


def at(day: int, hour: int, minute: int = 0) -> dt.datetime:
    return dt.datetime(2026, 11, day, hour, minute, tzinfo=SEOUL)


def when(written: dt.datetime, store: dict = CHOONGJANG, now: dt.datetime = TUESDAY_0902) -> tuple[str, dt.datetime]:
    found = schedule.post_time({"written_at": written.isoformat()}, store, now)
    return found["kind"], found["post_at"]


def test_p1_monday_review_goes_to_saturday_morning():
    assert when(at(16, 19, 45)) == ("weekday_to_weekend", at(21, 11))


def test_p2_thursday_late_review_still_saturday():
    assert when(at(19, 23, 50), now=at(19, 23, 55)) == ("weekday_to_weekend", at(21, 11))


def test_p3_friday_review_goes_to_next_lunch_after_24_hours():
    found = schedule.post_time({"written_at": at(20, 19).isoformat()}, CHOONGJANG, at(20, 19, 5))
    assert (found["kind"], found["post_at"], found["label"]) == ("weekend_next_peak", at(22, 11), "점심 한 시간 전")


def test_p4_saturday_afternoon_review_goes_to_sunday_dinner_peak():
    assert when(at(21, 13), now=at(21, 13, 5)) == ("weekend_next_peak", at(22, 16))  # 초옹장 저녁 피크 5시
    assert when(at(21, 13), PLAIN, now=at(21, 13, 5)) == ("weekend_next_peak", at(22, 17))  # 모르는 가게는 저녁 6시


def test_p5_sunday_reviews_already_past_monday_go_to_tuesday_lunch():
    assert when(at(15, 12, 30)) == ("weekend_next_peak", at(17, 11))
    assert when(at(15, 20, 5)) == ("weekend_next_peak", at(17, 11))


def test_p6_default_peaks():
    assert [m.strftime("%H:%M") for m, _ in schedule.slots(PLAIN, dt.date(2026, 11, 17), 1)] == ["11:00", "17:00"]


@pytest.mark.parametrize("first_peak, expected", [("13:00", (11, 30)), ("11:00", (10, 30)), ("12:00", (11, 0))])
def test_p7_weekend_morning_kept_between_1030_and_1130(first_peak, expected):
    store = {**CHOONGJANG, "peak_hours": {"lunch": first_peak, "dinner": "18:00"}}
    assert when(at(16, 19, 45), store) == ("weekday_to_weekend", at(21, *expected))


def test_p8_closed_sunday_moves_to_monday():
    store = {**CHOONGJANG, "closed_weekdays": [6]}
    assert when(at(20, 19), store, now=at(20, 19, 5)) == ("weekend_next_peak", at(23, 11))


def test_p9_weather_changes_words_not_time():
    data = {"weather": [{"date": "2026-11-17", "rain_chance": 0.7, "temp_max": 11}, {"date": "2026-11-19", "rain_chance": 0.8}],
            "event": [], "game": []}
    sunday = schedule.occasion_for({"written_at": at(15, 20, 5).isoformat()}, data, CHOONGJANG, TUESDAY_0902)
    assert sunday["post_at"] == at(17, 11) and sunday["context"]["rain"] is True and sunday["template"] == "weather"
    assert schedule.card_text(sunday, [], "옹심이") == "비 오는 날 옹심이 권하기"
    monday = schedule.occasion_for({"written_at": at(16, 19, 45).isoformat()}, data, CHOONGJANG, TUESDAY_0902)
    assert monday["post_at"] == at(21, 11)  # 목요일 비는 이 답글의 시각을 당기지 않는다
    assert monday["context"]["rain"] is False and schedule.card_text(monday, []) == "주말에 리뷰를 많이 봐요"


def test_p13_posted_replies_show_on_platform():
    from voice.tests.conftest import choongjang

    from voice.context import load
    from voice.jobs import batch_ask

    donna = choongjang(at=None)
    for review_id in ("rv_0401", "rv_0405", "rv_0409"):  # s005 칭찬 답글은 사원: 브리핑에서 "응"한 것으로 둔다 (인사과 4-b)
        batch_ask.KINDS["positive_reply"].approve(load("s005"), review_id)
    donna.clock("2026-11-17T11:00:00+09:00")
    items = {i["id"]: i for i in donna.get("/v1/dev/platform")["items"]}
    for review_id in ("rv_0401", "rv_0405"):
        assert items[review_id]["reply"]["posted_label"] == "오전 11시" and "옹심이" in items[review_id]["reply"]["text"]
    assert items["rv_0409"]["reply"] is None  # 토요일에 올라간다
