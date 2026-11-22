"""감사팀 5단계: 새 기준마다 코드 판정, 지적 문장, 묻지 않는 조건 (감사팀 계획 7-2). 가짜 판정(found/quotes)을 넣는다."""

import dataclasses
import datetime as dt

import pytest

from Harness.grounding import Evidence
from Harness.spec import RunContext
from Harness.tests.fakes import NOW, FakeClova, call, make_snapshot
from voice.audit import inspector
from voice.context import load, run_context
from voice.tests.test_agents import GOOD, critic_pass, loaded


@pytest.fixture(autouse=True)
def key(clova_on):
    """CLOVA 키를 넣는다 (가짜 CLOVA 는 각 시험이 맥락의 post 로 준다)."""


def judged(*quotes):
    return [call("submit_judgement", {"found": bool(quotes), "quotes": list(quotes)})]


def ctx(*turns, facts=()):
    fake = FakeClova(*turns)
    return RunContext(snapshot=make_snapshot(), now=NOW, post=fake, store_facts=list(facts)), fake


def test_card_promise():
    action = "배달 칼국수는 면과 국물을 따로 담아 주세요"
    c, _ = ctx(judged())
    found = inspector.card_promise("늦어서 죄송합니다. 더 신경 쓰겠습니다.", action, c)
    assert found.status == "fail" and found.criterion == "card_promise"
    assert found.reason == f"교정 카드 조치('{action}')를 하겠다는 말이 없어요. 사과와 함께 이 조치를 한 문장으로 넣어 주세요"
    c, _ = ctx(judged("면과 국물을 따로 담겠습니다"))
    assert inspector.card_promise("죄송합니다. 면과 국물을 따로 담겠습니다.", action, c) is None


def test_occasion_claim():
    c, fake = ctx(judged("비 오는 날엔"))
    found = inspector.occasion_claim("감사해요! 비 오는 날엔 칼국수예요.", "주말 (주말), 토요일: 그날 특별한 일은 없어요", c)
    assert found.reason == "올리는 날 정보에 없는 이야기예요: '비 오는 날엔'. 빼거나 올리는 날 정보에 맞게 고쳐 주세요"
    assert fake.requests[0]["messages"][1]["content"].startswith('올리는 날 정보: "주말')


def test_fix_relevance():
    c, _ = ctx(judged())
    found = inspector.fix_relevance("테이블 닦기", "손님이 나가면 닦아 주세요", "국물이 다 새서", c)
    assert found.reason == "이 할 일은 리뷰 불만('국물이 다 새서')을 줄이지 않아요. 그 불만을 직접 줄이는 행동으로 써 주세요"


def test_field_link_and_today_need_number_the_task():
    # 코드가 행동을 나누고 행동마다 근거 때문에 필요한지 묻는다: 우산꽂이는 필요, 메뉴판은 아님
    c, fake = ctx(judged("우산꽂이를 내놓고"), judged())
    found = inspector.field_link("우산꽂이", "우산꽂이를 내놓고 메뉴판도 새로 닦아 주세요", "오후 2시부터 비", "오후 2시부터 비", c, 2)
    assert found.reason == "2번째 할 일의 '메뉴판도 새로 닦아 주세요'는 근거('오후 2시부터 비')와 상관없어요" and fake.done()
    assert fake.requests[1]["messages"][1]["content"].startswith('근거: "오후 2시부터 비"\n행동: "메뉴판도 새로 닦아 주세요"')
    c, _ = ctx(judged())
    found = inspector.today_need("창고 정리", "창고 선반을 정리해 주세요", "오후 2시부터 비", c, 3)
    assert found.reason == "3번째 할 일은 오늘 안 해도 손님이 바로 겪지 않아요. today_impact 를 false 로 내 주세요"


def test_manual_angle_caption():
    c, _ = ctx(judged("주문서를 맞춰 보고"), judged())
    assert inspector.manual_added("대조", "주문서를 맞춰 보고 손님께 전화로 확인해 주세요", ["주문서 확인"], c).reason == \
        "'손님께 전화로 확인해 주세요'는 반복해서 넣은 할 일에 없는 행동이에요. 빼 주세요"
    c, _ = ctx(judged("군만두"))
    assert inspector.angle_menu("바삭한 군만두 점심", ["들깨칼국수"], c).reason == "이야기 '군만두'는 고른 메뉴와 상관없어요"
    c, _ = ctx(judged("떡볶이"))
    assert inspector.caption_off("칼국수 한 그릇! 떡볶이도 있어요.", ["들깨칼국수"], "추운 날", c).reason == \
        "'떡볶이'는 올릴 메뉴·이야기와 상관없어요"


@pytest.mark.parametrize("text, expected", [
    ("국물 용기는 랩을 두 번 씌우고 테이프를 붙여 주세요.", ["국물 용기는 랩을 두 번 씌우고", "테이프를 붙여 주세요"]),
    ("국물을 내기 전에 맛보고, 남은 육수는 버려 주세요", ["국물을 내기 전에 맛보고", "남은 육수는 버려 주세요"]),
    ("손님이 드나든 뒤 입구 문이 닫혔는지 봐 주세요", ["손님이 드나든 뒤 입구 문이 닫혔는지 봐 주세요"]),
    ("냉장고 문을 닫아 주세요", ["냉장고 문을 닫아 주세요"]),
])
def test_split_actions(text, expected):
    assert inspector.split_actions(text) == expected


def test_store_claim_checks_registered_facts():
    c, _ = ctx(judged("국내산 들깨만 써서"), facts=["국내산 들깨만 써요"])
    assert inspector.store_claim("국내산 들깨만 써서 고소해요.", c) is None
    c, _ = ctx(judged("30년 전통 비법 육수로"))
    found = inspector.store_claim("30년 전통 비법 육수로 끓였어요.", c)
    assert found.reason == "가게가 등록한 사실에 없는 이야기예요: '30년 전통 비법 육수로'"


def test_holiday_says():
    c, fake = ctx(judged())
    found = inspector.holiday_says("12월 25일에도 정상 영업합니다", dt.date(2026, 12, 25), c)
    assert found.reason == "'12월 25일에도 정상 영업합니다'는 12월 25일에 쉰다는 말이 아니에요. 그 날짜를 빼 주세요"
    assert '날짜: "12월 25일 (2026-12-25)"' in fake.requests[0]["messages"][1]["content"]


def test_question_that_cannot_be_asked_is_unchecked():
    c, _ = ctx(500, 500, 500)
    assert inspector.angle_menu("추운 날 칼국수", ["들깨칼국수"], c) == inspector.UNCHECKED


def test_first_failing_criterion_stops(reply_ctx):
    offer = "다음 주문 때 음료 서비스로 드릴게요."
    c, fake = reply_ctx(judged(offer))  # 첫 기준(보상)에 걸리면 뒤 기준(교정 카드 조치 약속)은 묻지 않는다
    verdict = inspector.reply({"text": f"늦어서 죄송합니다. {offer}"}, Evidence([]), {"review_id": "rv_0412", "fix": FIX}, c)
    assert verdict.status == "fail" and verdict.detail["criterion"] == "COMPENSATION" and verdict.detail["calls"] == 1
    assert fake.done()


def test_not_actionable_asks_nothing():
    c, fake = ctx()
    verdict = inspector.fix_card({"actionable": False, "quote": "x"}, Evidence([]), {"review_id": "x"}, c)
    assert verdict.status == "pass" and fake.requests == []


@pytest.fixture
def reply_ctx(clova_on):
    loaded()
    view = load("s001")

    def make(*turns):
        fake = FakeClova(*turns)
        return dataclasses.replace(run_context(view), post=fake), fake

    return make


FIX = {"cause": "배달이 늦었대요", "action": "배달 주문이 들어오면 바로 포장해 주세요", "reply": "x"}


def test_negative_reply_asks_card_promise_only_with_a_card(reply_ctx):
    c, fake = reply_ctx(*critic_pass(), judged())
    verdict = inspector.reply({"text": GOOD}, Evidence([]), {"review_id": "rv_0412", "fix": FIX}, c)
    assert verdict.status == "fail" and verdict.detail["criterion"] == "card_promise" and fake.done()
    c, fake = reply_ctx()  # 카드가 없으면 조치 약속을 묻지 않는다 (기존 기준은 같은 글이라 캐시)
    assert inspector.reply({"text": GOOD}, Evidence([]), {"review_id": "rv_0412"}, c).status == "pass" and fake.requests == []


def test_revise_does_not_ask_card_promise(reply_ctx):
    c, fake = reply_ctx(*critic_pass())
    task = {"review_id": "rv_0412", "fix": FIX, "revise": {"previous": "x", "instruction": "짧게"}}
    assert inspector.reply({"text": GOOD}, Evidence([]), task, c).status == "pass" and fake.done()


@pytest.mark.parametrize("criterion, given, output, answer, expected", [
    ("card_promise", {"action": "랩을 두 번"}, {"text": "죄송해요"}, judged(), False),
    ("holiday_says", {"date": "2026-12-25"}, {"quote": "12월 25일은 쉽니다"}, judged("12월 25일은 쉽니다"), True),
    ("angle_menu", {"menus": ["만두"]}, {"angle": "만두 이야기"}, 500, None),
])
def test_judge_case(criterion, given, output, answer, expected):
    c, _ = ctx(*([answer] * (3 if answer == 500 else 1)))
    assert inspector.judge_case(criterion, given, output, c) is expected
