"""현장 변수 사원 (voice/agents/field_tasks.py, 에이전트 조직 개편 5단계).

초옹장 11/17 09:02: 14시부터 비(70%), 12시 단체 12명 예약 메모 "땅콩 알레르기 손님 1명 있어요".
"""

import pytest

from Harness.tests.fakes import FakeClova, call
from voice import config, proposals, repo, staff
from voice.agents import field_tasks
from voice.context import load
from voice.tests.conftest import choongjang

LOOK = [call("get_today_weather", {}), call("get_today_reservations", {})]
ALLERGY = {"title": "땅콩 알레르기 확인", "detail": "12시 단체 손님 음식에 땅콩이 들어가는지 주방에 먼저 확인해 주세요",
           "phase": "open", "today_impact": True, "source_type": "reservation", "source_id": "rs_0031", "quote": "땅콩 알레르기 손님 1명 있어요"}
UMBRELLA = {"title": "우산꽂이 내놓기", "detail": "비 오기 전에 입구에 우산꽂이를 내놓아 주세요", "phase": "open",
            "today_impact": False, "source_type": "weather", "source_id": "weather:2026-11-17", "quote": "14시부터 비"}


def judged(*quotes):
    return [call("submit_judgement", {"found": bool(quotes), "quotes": list(quotes)})]


def submit(*items):
    return [call("submit_field_tasks", {"items": list(items)})]


@pytest.fixture
def agent(clova_on, monkeypatch):
    monkeypatch.setattr(config, "agent_on", lambda name: False)
    choongjang(at=None)

    def use(*turns):
        monkeypatch.setattr(config, "agent_on", lambda name: name == "field")
        return clova_on(FakeClova(*turns))

    return use


def field_proposals() -> list[dict]:
    return [p for p in repo.all_of(proposals.KIND, "s005") if p["by"] == "field_variable"]


def test_proposes_from_weather_and_reservation_memo_once(agent):
    fake = agent(LOOK, submit(ALLERGY, UMBRELLA), judged(), judged())
    made = field_tasks.propose_today(load("s005"))
    assert [p["payload"]["title"] for p in made] == ["땅콩 알레르기 확인", "우산꽂이 내놓기"] and fake.done()
    assert all(p["ask_on"] == "2026-11-17" and p["dept"] == "quality" for p in made)
    assert made[0]["reason"]["why"] == "예약 메모에 '땅콩 알레르기 손님 1명 있어요'라고 있어요."
    assert field_tasks.propose_today(load("s005")) == []  # 하루 한 번


def test_allergy_must_match_the_memo(agent):
    shrimp = {**ALLERGY, "title": "새우 알레르기 확인", "detail": "단체 손님 중 새우 알레르기 손님 음식을 따로 담아 주세요"}
    fake = agent(LOOK, submit(shrimp), submit(ALLERGY), judged())
    assert [p["payload"]["title"] for p in field_tasks.propose_today(load("s005"))] == ["땅콩 알레르기 확인"]
    assert "메모에 적힌 그대로" in fake.tool_messages(2)[-1] and fake.done()


def test_quote_must_come_from_its_source(agent):
    wrong = {**UMBRELLA, "quote": "하루 종일 눈"}
    fake = agent(LOOK, submit(wrong), submit(UMBRELLA), judged())
    assert len(field_tasks.propose_today(load("s005"))) == 1
    assert "글자 그대로" in fake.tool_messages(2)[-1] and fake.done()


def test_nothing_needed_is_fine(agent):
    agent(LOOK, submit())
    assert field_tasks.propose_today(load("s005")) == [] and field_proposals() == []
    assert field_tasks.propose_today(load("s005")) == []  # 빈 목록도 하루 한 번


def test_today_impact_becomes_urgent_when_applied(agent):
    agent(LOOK, submit(ALLERGY), judged())
    [made] = field_tasks.propose_today(load("s005"))
    task = proposals.apply(made["id"], "owner_yes")
    assert task["origin"] == "field_variable" and task["urgent"] is True and task["must_confirm"] is True
    [shown] = [t for t in staff.store_tasks("s005") if t["id"] == task["id"]]
    assert shown["source"]["by"] == "field_variable"
