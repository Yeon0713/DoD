"""팀장 LLM 과 부서 보고, 부서 사이 충돌 (voice/departments.py, agents/team_lead.py, 에이전트 조직 개편 7단계)."""

import pytest

from Harness.tests.fakes import FakeClova, call
from voice import clock, config, departments, marketing, proposals, repo
from voice.context import load
from voice.jobs import staff_tasks
from voice.tests.conftest import choongjang

SEAL = {"title": "배달 용기 이중 실링", "detail": "국물 메뉴는 랩을 두 번 씌우고 뚜껑에 테이프를 한 번 더 붙여 주세요",
        "phase": "open", "days": 2, "must_confirm": True, "urgent": False}
UMBRELLA = {"title": "우산꽂이 내놓기", "detail": "입구에 우산꽂이를 내놓아 주세요", "phase": "open", "repeat": "today", "days": 1,
            "must_confirm": True, "urgent": False}


def propose(dept: str, by: str, payload: dict, review_id: str | None = None) -> dict:
    reason = {"type": "review", "review_id": review_id} if review_id else {"type": "weather", "why": "오늘 14시부터 비가 와요."}
    return proposals.create("s005", dept=dept, by=by, payload=payload, ask_on=clock.now().date().isoformat(), reason=reason,
                            link={"review_id": review_id} if review_id else {})


def lead(pid: str, verdict: str, reason: str = "") -> dict:
    return {"id": pid, "verdict": verdict, "reason": reason}


@pytest.fixture
def leads(clova_on, monkeypatch):
    monkeypatch.setattr(config, "agent_on", lambda name: False)
    choongjang(at=None)  # 픽스처의 면 교정 제안은 팀장이 꺼진 채로 이미 남았다 (FALLBACK)

    def use(*turns):
        monkeypatch.setattr(config, "agent_on", lambda name: name == "lead")
        return clova_on(FakeClova(*turns))

    return use


def test_lead_drops_one_and_orders_the_rest(leads):
    seal = propose("customer", "negative_review", SEAL, "rv_x")
    umbrella = propose("quality", "field_variable", UMBRELLA)
    fake = leads(
        [call("submit_lead", {"items": [lead(seal["id"], "keep")], "order": [seal["id"]], "summary": "교정 하나"})],
        [call("submit_lead", {"items": [lead(umbrella["id"], "drop", "비가 오후 늦게라 지금은 필요 없어요")], "order": [],
                              "summary": "오늘은 없어요"})],
    )
    departments.run_leads(load("s005"))
    assert proposals.get(umbrella["id"])["state"] == "dropped" and fake.done()
    asked = [p["id"] for p in proposals.for_briefing("s005", clock.now().date().isoformat())]
    assert seal["id"] in asked and umbrella["id"] not in asked
    report = repo.get(departments.KIND, departments.report_id("s005", clock.now().date().isoformat(), "quality"))
    assert report["verdicts"][umbrella["id"]]["verdict"] == "drop" and report["source"] == "AGENT"


def test_lead_must_judge_every_item(leads):
    seal = propose("customer", "negative_review", SEAL, "rv_x")
    fake = leads([call("submit_lead", {"items": [], "order": [], "summary": "없음"})],
                 [call("submit_lead", {"items": [lead(seal["id"], "keep")], "order": [seal["id"]], "summary": "교정 하나"})])
    departments.run_leads(load("s005"))
    assert proposals.get(seal["id"])["lead"]["source"] == "AGENT"
    assert "한 번씩 판단" in fake.tool_messages(1)[-1]


def test_lead_failure_keeps_everything(leads):
    seal = propose("customer", "negative_review", SEAL, "rv_x")
    leads(500)
    departments.run_leads(load("s005"))
    found = proposals.get(seal["id"])
    assert found["state"] == "proposed" and found["lead"]["source"] == "FALLBACK"


def test_realtime_alert_goes_through_the_lead(leads):
    donna = choongjang(permission=None)
    next_id = f"pr_{repo.counters_of('s005').get('proposal:s005', 0) + 1:04d}"  # 이 리뷰로 생길 제안
    leads([call("submit_lead", {"items": [{"id": next_id, "verdict": "drop", "reason": "이미 매뉴얼에 있어요"}], "order": [],
                                "summary": "뺐어요"})])
    donna.clock("2026-11-17T15:40:00+09:00")
    rid = donna.demo_review("leak")
    record = repo.get("alert", f"al_{rid}")
    assert record["card"] is None and proposals.get(record["proposal_id"])["state"] == "dropped"


def test_marketing_plan_on_a_complained_menu_is_dropped():
    choongjang(at=None)
    repo.save_review({"id": "rv_t1", "store_id": "s005", "sentiment": "negative", "rating": 2, "reply_status": "posted",
                      "text": "들깨옹심이 국물이 다 식어서 왔어요", "written_at": clock.iso(clock.now())})
    view = load("s005")
    plan_id = marketing.plan_id("s005", view.now.date().isoformat())
    assert departments.complained_menus(view) == {"m_3"}  # 들깨옹심이
    complained = "m_3"
    repo.put(marketing.KIND, plan_id, "s005", {"store_id": "s005", "date": view.now.date().isoformat(), "menu_ids": [complained],
                                               "angle": "x", "body": None, "hashtags": [], "lead": None})
    assert departments.cross_check(load("s005"))
    assert marketing.today(load("s005")) is None  # 인스타는 지금 규칙(많이 나간 메뉴)으로 돌아간다


def test_why_lines_for_lead_input():
    choongjang(at=None)
    p = propose("quality", "field_variable", UMBRELLA)
    assert staff_tasks._why(load("s005"), p, clock.now()) == "오늘 14시부터 비가 와요."


def test_long_summary_says_how_long(leads):
    """팀장 summary 가 길면 지금 몇 자인지 알린다. "폭 34 이하"만 듣고 두 번 다 넘겨 판단 없이 남은 적이 있다 (2026-11-21)."""
    seal = propose("customer", "negative_review", SEAL, "rv_x")
    long = "고객 응대 부서는 면이 불지 않게 배달하기 위해 배달 주문 시 면을 따로 포장합니다."
    fake = leads([call("submit_lead", {"items": [lead(seal["id"], "keep")], "order": [seal["id"]], "summary": long})],
                 [call("submit_lead", {"items": [lead(seal["id"], "keep")], "order": [seal["id"]], "summary": "교정 하나"})])
    departments.run_leads(load("s005"))
    assert proposals.get(seal["id"])["lead"]["source"] == "AGENT" and fake.done()
    assert fake.tool_messages(1)[-1].startswith("거절: summary 칸이 길어요 (지금 ")
