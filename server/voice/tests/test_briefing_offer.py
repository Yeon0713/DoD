"""오전에 처음 "도나야"만 부르면 "오늘 브리핑을 시작할까요?" (dialog/turn.offer_briefing, 2026-11-22).

앱은 "도나야"만 들으면 turn(event: called)을 보낸다. 서버가 ask 로 답하면 그 질문을 띄우고, ignore 면 앱이 "네."라고 한다.
초옹장 H 픽스처(11/17 09:02, 브리핑 준비됨)로 본다.
"""

from voice import clock
from voice.tests.conftest import Choongjang, step_key


def h_fixture() -> Choongjang:
    donna = Choongjang()
    assert donna.client.post("/v1/dev/fixtures", json={"fixture": "s005_choongjang_h"}).json()["store_id"] == "s005"
    return donna


def test_first_call_in_the_morning_offers_the_briefing_and_yes_starts_it():
    donna = h_fixture()
    offer = donna.turn(event="called")
    assert offer["type"] == "ask" and offer["expects_reply"] is True and offer["ask"] == {"key": "start_briefing"}
    assert offer["headline"] == "오늘 브리핑을 시작할까요?" and [s["text"] for s in offer["say"]] == ["네. 오늘 브리핑을 시작할까요?"]
    assert [r["id"] for r in offer["cards"][0]["rows"]] == ["p_schedule", "p_reviews", "p_story", "p_request"]  # 홈 카드 그대로
    started = donna.turn("응")
    assert step_key(started) == "sum_weather" and started["headline"] == "오전 11시부터 비가 와요"
    # 브리핑을 들은 뒤에는 묻지 않는다 (앱이 "네.")
    assert donna.turn(event="called")["type"] == "ignore"


def test_no_closes_and_does_not_ask_again_that_day():
    donna = h_fixture()
    assert donna.turn(event="called")["type"] == "ask"
    no = donna.turn("아니")
    assert no["headline"] == "필요하실 때 불러 주세요" and [s["text"] for s in no["say"]] == ["네, 필요하실 때 불러 주세요."]
    assert donna.turn(event="called")["type"] == "ignore"
    # 직접 시키면 브리핑은 그대로 한다
    assert step_key(donna.turn("오늘 일정 브리핑해 줘", addressed=True)) == "sum_weather"


def test_afternoon_call_is_just_yes():
    donna = h_fixture()
    donna.client.post("/v1/dev/clock", json={"now": "2026-11-17T12:30:00+09:00"})
    assert clock.now().hour == 12
    assert donna.turn(event="called")["type"] == "ignore"
