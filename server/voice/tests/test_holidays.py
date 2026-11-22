"""쉬는 날 받기 (voice/holidays.py, 에이전트 조직 개편 6-3). 초옹장 11/17(화)."""

import datetime as dt

import pytest

from Harness.tests.fakes import FakeClova, call
from voice import config, holidays, hours, repo
from voice.context import load
from voice.instagram import posts
from voice.jobs import briefing
from voice.tests.conftest import choongjang, walk_to

TUE = dt.date(2026, 11, 17)


@pytest.mark.parametrize("words, day", [
    ("내일", "2026-11-18"), ("모레", "2026-11-19"), ("26일", "2026-11-26"), ("12월3일", "2026-12-03"),
    ("다음주수요일", "2026-11-25"), ("이번주금요일", "2026-11-20"), ("목요일", "2026-11-19"), ("15일", "2026-12-15"),
])
def test_parse_day(words, day):
    assert holidays.parse_day(words, TUE).isoformat() == day


def test_owner_says_a_day_off_and_confirms():
    donna = choongjang()
    asked = donna.turn("다음 주 수요일 쉬어", addressed=True)
    assert asked["type"] == "ask_holiday" and asked["say"][0]["text"] == "11월 25일 수요일을 쉬는 날로 적을게요. 맞아요?"
    assert hours.on(repo.store("s005"), dt.date(2026, 11, 25)) is not None  # 대답 전에는 그대로
    done = donna.turn("응")
    assert done["intent"] == "holiday.yes" and done["say"][0]["text"] == "네, 11월 25일 수요일은 쉬는 날로 적었어요."
    assert hours.on(repo.store("s005"), dt.date(2026, 11, 25)) is None
    canceled = donna.turn("25일 쉬는 거 취소해", addressed=True)
    assert canceled["type"] == "ask_holiday" and "취소할게요" in canceled["say"][0]["text"]
    donna.turn("응")
    assert hours.on(repo.store("s005"), dt.date(2026, 11, 25)) is not None


def test_owner_says_no_keeps_hours():
    donna = choongjang()
    donna.turn("내일 쉬어", addressed=True)
    assert donna.turn("아니")["say"][0]["text"] == "네, 그대로 둘게요."
    assert holidays.items(repo.store("s005")) == []


# 2차 감사(감사팀): 인용이 그 날 쉰다는 뜻인가
SAYS = [call("submit_judgement", {"found": True, "quotes": ["11월 26일(목) 가게 사정으로 하루 쉬어 갑니다"]})]


@pytest.fixture
def naver(clova_on, monkeypatch):
    monkeypatch.setattr(config, "agent_on", lambda name: False)
    donna = choongjang(at=None)
    monkeypatch.setattr(holidays, "naver_texts", lambda store_id: ["11월 26일(목) 가게 사정으로 하루 쉬어 갑니다"])

    def use(*turns):
        monkeypatch.setattr(config, "agent_on", lambda name: name == "holiday")
        clova_on(FakeClova(*turns))
        return donna

    return use


def test_naver_day_is_asked_in_the_morning_before_it_counts(naver):
    donna = naver([call("submit_holidays", {"items": [{"date": "2026-11-26", "quote": "11월 26일(목) 가게 사정으로 하루 쉬어 갑니다"}]})], SAYS)
    briefing.prepare("s005")
    [found] = holidays.items(repo.store("s005"))
    assert found == {"date": "2026-11-26", "source": "naver", "note": "11월 26일(목) 가게 사정으로 하루 쉬어 갑니다", "confirmed": False}
    assert hours.on(repo.store("s005"), dt.date(2026, 11, 26)) is not None  # 확인 전에는 쉬는 날이 아니다
    asked = walk_to(donna, "holiday")  # 요약과 상세 브리핑 물음 다음, 상세 첫머리에 묻는다
    assert asked["type"] == "ask_holiday" and asked["briefing"]["step_key"] == "holiday"
    assert [s["text"] for s in asked["say"]] == ["네이버 소식에 '11월 26일(목) 가게 사정으로 하루 쉬어 갑니다'라고 있어요.",
                                                "11월 26일 목요일을 쉬는 날로 적을게요. 맞아요?"]
    donna.turn("응")
    assert hours.on(repo.store("s005"), dt.date(2026, 11, 26)) is None


def test_naver_day_rejected_is_not_a_day_off(naver):
    donna = naver([call("submit_holidays", {"items": [{"date": "2026-11-26", "quote": "11월 26일(목) 가게 사정으로 하루 쉬어 갑니다"}]})], SAYS)
    briefing.prepare("s005")
    walk_to(donna, "holiday")
    donna.turn("아니")
    assert holidays.unconfirmed(repo.store("s005"), dt.date(2026, 11, 17)) == []  # 다시 묻지 않는다
    assert hours.on(repo.store("s005"), dt.date(2026, 11, 26)) is not None  # 쉬는 날이 아니다
    cancel = donna.turn("26일 휴무 취소해 줘", addressed=True)
    assert cancel["headline"] == "적힌 휴무가 없어요"


def test_naver_day_rejected_is_not_asked_again_next_day(naver):
    """다음 날 같은 네이버 글을 다시 읽어도 아니라고 한 날은 다시 묻지 않는다 (2026-11-22 버그 V5)."""
    item = {"items": [{"date": "2026-11-26", "quote": "11월 26일(목) 가게 사정으로 하루 쉬어 갑니다"}]}
    donna = naver([call("submit_holidays", item)], SAYS, [call("submit_holidays", item)])  # 다음 날 같은 글의 감사는 캐시
    briefing.prepare("s005")
    walk_to(donna, "holiday")
    assert donna.turn("아니")["headline"] == "그대로 둘게요"
    donna.clock("2026-11-18T09:30:00+09:00")
    briefing.prepare("s005")
    assert briefing.current("s005")["steps"]["holiday"] is None
    assert holidays.unconfirmed(repo.store("s005"), dt.date(2026, 11, 18)) == []
    assert hours.on(repo.store("s005"), dt.date(2026, 11, 26)) is not None


def test_naver_quote_must_be_in_the_text(naver):
    naver([call("submit_holidays", {"items": [{"date": "2026-11-26", "quote": "26일 휴무"}]})],
          [call("submit_holidays", {"items": []})])
    briefing.prepare("s005")
    assert holidays.items(repo.store("s005")) == []


def test_caption_says_tomorrow_is_a_day_off():
    choongjang()
    holidays.add("s005", "2026-11-18", source="owner", confirmed=True)
    assert posts.store_lines(load("s005"))[0] == "내일(11월 18일)은 쉬어요."
