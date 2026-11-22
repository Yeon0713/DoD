"""현장 변수 사원 (voice/agents/field_tasks.py, 에이전트 조직 개편 5단계).

초옹장 11/17 09:02: 14시부터 비(70%), 12시 단체 12명 예약 메모 "땅콩 알레르기 손님 1명 있어요".
2026-11-22: 예약 메모의 알레르기는 모델 없이 규칙으로 먼저 할 일을 만든다 (allergy_items, '12시 손님 땅콩 알레르기').
모델이 같은 예약을 근거로 낸 할 일은 버리고, 그 밖의 날씨·예약 할 일만 더한다.
"""

import pytest

from Harness.tests.fakes import FakeClova, call
from voice import config, proposals, repo, staff
from voice.agents import field_tasks
from voice.context import load
from voice.tests.conftest import choongjang

LOOK = [call("get_today_weather", {}), call("get_today_reservations", {})]
RULED = "12시 손님 땅콩 알레르기"  # 규칙이 예약 메모에서 만든 제목 (allergy_items)
ALLERGY = {"title": "땅콩 알레르기 확인", "detail": "12시 단체 손님 음식에 땅콩이 들어가는지 주방에 먼저 확인해 주세요",
           "phase": "open", "today_impact": True, "source_type": "reservation", "source_id": "rs_0031", "quote": "땅콩 알레르기 손님 1명 있어요"}
UMBRELLA = {"title": "우산꽂이 내놓기", "detail": "비 오기 전에 입구에 우산꽂이를 내놓아 주세요", "phase": "open",
            "today_impact": False, "source_type": "weather", "source_id": "weather:2026-11-17", "quote": "오후 2시부터 비"}


def judged(*quotes):
    return [call("submit_judgement", {"found": bool(quotes), "quotes": list(quotes)})]


# 2차 감사(감사팀)의 판정 차례: 할 일마다 알바생이 할 수 있나 → 행동마다 근거 때문에 필요한가 → (today_impact 면) 오늘 꼭 해야 하나
# (두 할 일 모두 행동이 하나다. 근거·오늘 질문은 예·아니오만 본다)
ALLERGY_OK = [judged(), judged("필요"), judged("오늘")]
UMBRELLA_OK = [judged(), judged("필요")]


def submit(*items):
    return [call("submit_field_tasks", {"items": list(items)})]


@pytest.fixture
def agent(clova_on, monkeypatch):
    monkeypatch.setattr(config, "agent_on", lambda name: False)
    with monkeypatch.context() as m:  # 픽스처의 밤사이 준비는 현장 변수 사원을 건너뛴다 (시험에서 직접 부른다. 하루 한 번이라)
        m.setattr(field_tasks, "propose_today", lambda view: [])
        choongjang(at=None)

    def use(*turns):
        monkeypatch.setattr(config, "agent_on", lambda name: name == "field")
        return clova_on(FakeClova(*turns))

    return use


def field_proposals() -> list[dict]:
    return [p for p in repo.all_of(proposals.KIND, "s005") if p["by"] == "field_variable"]


def test_proposes_from_weather_and_reservation_memo_once(agent):
    fake = agent(LOOK, submit(ALLERGY, UMBRELLA), *ALLERGY_OK, *UMBRELLA_OK)
    made = field_tasks.propose_today(load("s005"))
    # 알레르기는 규칙이 만든 것 하나만 (모델이 같은 예약으로 낸 '땅콩 알레르기 확인'은 버린다)
    assert [p["payload"]["title"] for p in made] == [RULED, "우산꽂이 내놓기"] and fake.done()
    assert made[0]["reason"]["id"] == "rs_0031" and made[0]["payload"]["today_impact"] is True
    assert all(p["ask_on"] == "2026-11-17" and p["dept"] == "quality" for p in made)
    assert made[0]["reason"]["why"] == "예약 메모에 '땅콩 알레르기 손님 1명 있어요'라고 있어요."
    assert field_tasks.propose_today(load("s005")) == []  # 하루 한 번


def test_allergy_must_match_the_memo(agent):
    shrimp = {**ALLERGY, "title": "새우 알레르기 확인", "detail": "단체 손님 중 새우 알레르기 손님 음식을 따로 담아 주세요"}
    fake = agent(LOOK, submit(shrimp), submit(ALLERGY), *ALLERGY_OK)
    assert [p["payload"]["title"] for p in field_tasks.propose_today(load("s005"))] == [RULED]
    assert "메모에 적힌 그대로" in fake.tool_messages(2)[-1] and fake.done()


def test_quote_must_come_from_its_source(agent):
    wrong = {**UMBRELLA, "quote": "하루 종일 눈"}
    fake = agent(LOOK, submit(wrong), submit(UMBRELLA), *UMBRELLA_OK)
    assert [p["payload"]["title"] for p in field_tasks.propose_today(load("s005"))] == [RULED, "우산꽂이 내놓기"]
    assert "글자 그대로" in fake.tool_messages(2)[-1] and fake.done()


def test_nothing_needed_is_fine(agent):
    """모델이 빈 목록을 내도 된다. 예약 메모의 알레르기만 규칙으로 남는다."""
    agent(LOOK, submit())
    assert [p["payload"]["title"] for p in field_tasks.propose_today(load("s005"))] == [RULED]
    assert [p["payload"]["title"] for p in field_proposals()] == [RULED]
    assert field_tasks.propose_today(load("s005")) == []  # 빈 목록도 하루 한 번


def test_today_impact_becomes_urgent_when_applied(agent):
    agent(LOOK, submit(ALLERGY), *ALLERGY_OK)
    [made] = field_tasks.propose_today(load("s005"))
    task = proposals.apply(made["id"], "owner_yes")
    assert task["origin"] == "field_variable" and task["urgent"] is True and task["must_confirm"] is True
    [shown] = [t for t in staff.store_tasks("s005") if t["id"] == task["id"]]
    assert shown["source"]["by"] == "field_variable"


def test_today_impact_is_asked_first(agent):
    """today_impact 는 팀장 없이 그대로 긴급이다 (2026-11-21 팀장 없앰). 브리핑에서도 먼저 묻는다."""
    agent(LOOK, submit(UMBRELLA, ALLERGY), *UMBRELLA_OK, *ALLERGY_OK)
    field_tasks.propose_today(load("s005"))
    asked = [p["payload"]["title"] for p in proposals.for_briefing("s005", "2026-11-17") if p["by"] == "field_variable"]
    assert asked == [RULED, "우산꽂이 내놓기"]


def test_allergy_cannot_ride_on_the_weather(agent):
    """알레르기 손님 정보는 그 예약 메모를 근거로 한 할 일에만 (날씨를 근거로 한 할 일에 섞으면 거절)."""
    mixed = {**UMBRELLA, "title": "땅콩 알레르기 손님 우산 준비", "detail": "땅콩 알레르기 손님이 비를 맞지 않게 우산을 준비하세요"}
    fake = agent(LOOK, submit(mixed), submit(UMBRELLA), *UMBRELLA_OK)
    assert [p["payload"]["title"] for p in field_tasks.propose_today(load("s005"))] == [RULED, "우산꽂이 내놓기"]
    assert "그 할 일의 근거에 없어요" in fake.tool_messages(2)[-1] and fake.done()


def test_too_long_title_says_which_field_and_how_long(agent):
    """폭 거절은 어느 칸이 지금 몇 자이고 몇 자까지인지 말한다. "길어요"만 듣고는 같은 제목을 다시 냈다 (2026-11-21)."""
    long_title = {**ALLERGY, "title": "땅콩 알레르기 손님 대체 메뉴 준비"}
    fake = agent(LOOK, submit(long_title), submit(ALLERGY), *ALLERGY_OK)
    assert [p["payload"]["title"] for p in field_tasks.propose_today(load("s005"))] == [RULED] and fake.done()
    assert "1번째 할 일의 title 칸이 길어요 (지금 16.5자, 16자까지" in fake.tool_messages(2)[-1]


def test_phase_is_chosen_in_korean_and_stored_as_code(agent):
    """phase 는 우리말로 고르고 코드로 바꿔 넣는다. 영어 값을 보이면 모델이 다른 값을 쓰려다 CLOVA 가 40009 로 버렸다 (2026-11-21 재현)."""
    assert field_tasks.ITEM["properties"]["phase"]["enum"] == ["문 열기 전", "영업 중", "마감"]
    fake = agent(LOOK, submit({**UMBRELLA, "phase": "문 열기 전"}), *UMBRELLA_OK)
    ruled, made = field_tasks.propose_today(load("s005"))
    assert ruled["payload"]["phase"] == "open"  # 규칙이 만든 알레르기 할 일은 영업 중
    assert made["payload"]["phase"] == "before_open" and fake.done()


def test_allergy_memo_needs_no_model(agent):
    """에이전트가 꺼져 있어도 예약 메모의 알레르기는 규칙으로 할 일이 된다 (메모에 적힌 이름 그대로, 오늘만)."""
    [made] = field_tasks.propose_today(load("s005"))
    assert made["payload"]["title"] == RULED and made["payload"]["repeat"] == "today"
    assert made["reason"] == {"type": "reservation", "id": "rs_0031", "quote": "땅콩 알레르기 손님 1명 있어요", "date": "2026-11-17",
                              "why": "예약 메모에 '땅콩 알레르기 손님 1명 있어요'라고 있어요."}
    assert field_tasks.propose_today(load("s005")) == []  # 하루 한 번
