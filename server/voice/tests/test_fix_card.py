"""부정 리뷰 사원: 교정 카드를 LLM 으로 쓰기 (voice/agents/fix_card.py, 에이전트 조직 개편 3단계).

초옹장 픽스처의 밤사이 리뷰 rv_0412 "면이 불어서 왔어요." 로 본다. 가짜 CLOVA 가 정해 둔 차례대로 답한다.
"""

import pytest

from Harness.tests.fakes import FakeClova, call
from voice import config
from voice.agents import fix_card
from voice.context import load
from voice.tests.conftest import choongjang

GOOD = {"actionable": True, "quote": "면이 불어서 왔어요", "title": "배달 면 따로 담기", "detail": "배달 칼국수는 면과 국물을 따로 담아 주세요"}


def judged(*quotes):
    return [call("submit_judgement", {"found": bool(quotes), "quotes": list(quotes)})]


CARD_OK = [judged(), judged("면과 국물을 따로 담아 주세요")]  # 2차 감사(감사팀): 알바생이 할 수 있나 → 불만의 원인을 막나


@pytest.fixture
def agent(clova_on, monkeypatch):
    """픽스처 준비는 에이전트를 끈 채로 하고, 그 뒤 교정 카드 에이전트만 켠다."""
    monkeypatch.setattr(config, "agent_on", lambda name: False)
    choongjang(at=None)

    def use(*turns):
        monkeypatch.setattr(config, "agent_on", lambda name: name == "fixcard")
        return clova_on(FakeClova(*turns))

    return use


def card(rid="rv_0412") -> dict:
    view = load("s005")
    return fix_card.card_for(view, view.review(rid))


def test_agent_card_replaces_template(agent):
    fake = agent([call("submit_fix_card", GOOD)], *CARD_OK)
    found = card()
    assert found["card_source"] == "AGENT" and found["card"] == {"title": GOOD["title"], "detail": GOOD["detail"]}
    assert found["reply"] == found["plain"] and found["quote"] == "면이 불어서 왔어요" and fake.done()


def test_something_staff_cannot_do_is_rejected(agent):
    buy = {**GOOD, "title": "새 포장 용기 사기", "detail": "국물이 안 새는 새 용기를 사서 써 주세요"}
    fake = agent([call("submit_fix_card", buy)], judged("새 용기를 사서"), [call("submit_fix_card", GOOD)], *CARD_OK)
    assert card()["card"]["title"] == GOOD["title"]
    assert "할 수 없는 일" in fake.tool_messages(2)[0] and fake.done()


def test_not_actionable_makes_no_card(agent):
    fake = agent([call("submit_fix_card", {"actionable": False, "quote": "면이 불어서 왔어요", "title": "", "detail": ""})])
    found = card()
    assert found["card"] is None and found["card_source"] == "NONE" and fake.done()  # 판정 질문은 부르지 않는다


def test_quote_must_be_in_the_review(agent):
    made_up = {**GOOD, "quote": "국물이 차가웠어요"}
    fake = agent([call("submit_fix_card", made_up)], [call("submit_fix_card", GOOD)], *CARD_OK)
    assert card()["card_source"] == "AGENT"
    assert "글자 그대로" in fake.tool_messages(1)[0] and fake.done()


def test_falls_back_to_template_when_clova_fails(agent):
    agent(500)
    found = card()
    assert found["card_source"] == "TEMPLATE" and found["card"]["title"] == "배달 칼국수 면·국물 따로 담기"


def test_too_long_title_says_how_long(agent):
    long = {**GOOD, "title": "주문한 음식이 잘 나갔는지 확인하기"}
    fake = agent([call("submit_fix_card", long)], [call("submit_fix_card", GOOD)], *CARD_OK)
    assert card()["card_source"] == "AGENT" and fake.done()
    assert "title 칸이 길어요 (지금 17자, 16자까지" in fake.tool_messages(1)[-1]
