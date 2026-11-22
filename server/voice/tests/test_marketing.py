"""마케팅 부서 (voice/marketing.py, agents/topic_finder.py, agents/caption_writer.py, 에이전트 조직 개편 6단계).

초옹장 11/17. 메뉴 m_1~m_4 모두 사진이 있다.
"""

import pytest

from Harness.tests.fakes import FakeClova, call
from voice import config, marketing
from voice.context import load
from voice.instagram import posts
from voice.tests.conftest import FakeGraph
from voice.tests.test_instagram import Choongjang, chj, connect  # noqa: F401 (chj 는 fixture)

LOOK = [call("get_top_menus", {}), call("get_liked", {})]
TOPIC = {"menu_ids": ["m_1", "m_3"], "angle": "비 오는 날 고소한 들깨 국물", "evidence": ["좋아한 점: 들깨 국물"]}
CAPTION = {"body": "비 오는 날엔 고소한 들깨 국물 한 그릇 어떠세요? 쫀득한 옹심이까지 따뜻하게 준비해 둘게요.",
           "hashtags": ["#초옹장", "#들깨옹심이", "#비오는날"]}


def judged(*quotes):
    return [call("submit_judgement", {"found": bool(quotes), "quotes": list(quotes)})]


TOPIC_OK = [judged()]  # 2차 감사(감사팀): 고른 메뉴가 아닌 음식 (angle_menu)
CAPTION_OK = [judged(), judged()]  # 메뉴·이야기 밖 이야기 (caption_off) → 가게 사실 주장 (store_claim)


@pytest.fixture
def agents(chj: Choongjang, ig_on, clova_on, monkeypatch):
    ig_on(FakeGraph())
    connect(chj)

    def use(*turns):
        monkeypatch.setattr(config, "agent_on", lambda name: name in ("topic", "caption"))
        return clova_on(FakeClova(*turns))

    return use


def test_plan_picks_menus_and_writes_caption(agents):
    fake = agents(LOOK, [call("submit_topic", TOPIC)], *TOPIC_OK, [call("submit_caption", CAPTION)], *CAPTION_OK)
    plan = marketing.plan_today(load("s005"))
    assert plan["menu_ids"] == ["m_1", "m_3"] and plan["body"] == CAPTION["body"] and fake.done()
    built = posts.build_feed(load("s005"))
    assert [s["title"] for s in built["slides"][:3]] == ["들깨옹심이메밀칼국수", "들깨옹심이", "멸치옹심이메밀칼국수"]
    assert built["caption"].startswith(CAPTION["body"] + "\n#초옹장 #들깨옹심이 #비오는날")
    assert built["caption"].endswith("영업시간 10:30 ~ 20:30\n#초옹장")  # 가게 정보는 코드가 붙인다
    assert marketing.plan_today(load("s005")) is None  # 하루 한 번


def test_topic_needs_menus_with_photos(agents):
    no_photo = {**TOPIC, "menu_ids": ["m_9"]}  # 없는 메뉴
    fake = agents(LOOK, [call("submit_topic", no_photo)], [call("submit_topic", TOPIC)], *TOPIC_OK, [call("submit_caption", CAPTION)], *CAPTION_OK)
    assert marketing.plan_today(load("s005"))["menu_ids"] == ["m_1", "m_3"]
    assert "사진이 있는 메뉴" in fake.tool_messages(2)[-1]


def test_sales_claim_needs_sales_data(agents):
    bragging = {**TOPIC, "angle": "요즘 제일 인기 많은 들깨 국물"}
    fake = agents([call("get_liked", {})], [call("submit_topic", bragging)], [call("submit_topic", TOPIC)], *TOPIC_OK,
                  [call("submit_caption", CAPTION)], *CAPTION_OK)
    assert marketing.plan_today(load("s005"))["angle"] == TOPIC["angle"]
    assert "매출을 본 뒤에만" in fake.tool_messages(2)[-1]


def test_too_many_hashtags_rejected(agents):
    tags = {**CAPTION, "hashtags": [f"#태그{i}" for i in range(9)]}
    fake = agents(LOOK, [call("submit_topic", TOPIC)], *TOPIC_OK, [call("submit_caption", tags)], [call("submit_caption", CAPTION)], *CAPTION_OK)
    assert marketing.plan_today(load("s005"))["hashtags"] == CAPTION["hashtags"]
    assert "8개까지만" in fake.tool_messages(4)[-1]  # 요청 2 는 소재 감사 질문


def test_no_plan_keeps_the_rule_feed(chj: Choongjang, ig_on):
    ig_on(FakeGraph())
    connect(chj)
    built = posts.build_feed(load("s005"))
    assert built["caption"].startswith("이번 달 가장 많이 나간 메뉴예요.")
