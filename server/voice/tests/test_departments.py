"""부서 보고와 부서 사이 충돌 (voice/departments.py, 에이전트 조직 개편 7단계). 팀장은 2026-11-21 없앰 (agent-structure.md 5장)."""

from voice import clock, departments, marketing, proposals, repo
from voice.context import load
from voice.jobs import staff_tasks
from voice.tests.conftest import choongjang

SEAL = {"title": "배달 용기 이중 실링", "detail": "국물 메뉴는 랩을 두 번 씌우고 뚜껑에 테이프를 한 번 더 붙여 주세요",
        "phase": "open", "days": 2, "must_confirm": True, "urgent": False}
UMBRELLA = {"title": "우산꽂이 내놓기", "detail": "입구에 우산꽂이를 내놓아 주세요", "phase": "open", "repeat": "today", "days": 1,
            "must_confirm": True, "urgent": False}
ALLERGY = {"title": "땅콩 알레르기 확인", "detail": "12시 단체 손님 음식에 땅콩이 들어가는지 주방에 먼저 확인해 주세요",
           "phase": "open", "repeat": "today", "days": 1, "must_confirm": True, "urgent": False, "today_impact": True}


def propose(dept: str, by: str, payload: dict, review_id: str | None = None) -> dict:
    reason = {"type": "review", "review_id": review_id} if review_id else {"type": "weather", "why": "오늘 14시부터 비가 와요."}
    return proposals.create("s005", dept=dept, by=by, payload=payload, ask_on=clock.now().date().isoformat(), reason=reason,
                            link={"review_id": review_id} if review_id else {}, dedupe=False)


def today() -> str:
    return clock.now().date().isoformat()


def test_order_is_urgent_then_dept_then_arrival():
    choongjang(at=None)
    umbrella = propose("quality", "field_variable", UMBRELLA)
    seal = propose("customer", "negative_review", SEAL, "rv_x")
    allergy = propose("quality", "field_variable", ALLERGY)
    mine = {umbrella["id"], seal["id"], allergy["id"]}
    asked = [p["id"] for p in proposals.for_briefing("s005", today()) if p["id"] in mine]
    assert asked == [allergy["id"], seal["id"], umbrella["id"]]  # 긴급(today_impact) → 고객 응대 → 품질 관리


def test_report_keeps_everything_in_code_order():
    choongjang(at=None)
    umbrella = propose("quality", "field_variable", UMBRELLA)
    allergy = propose("quality", "field_variable", ALLERGY)
    departments.run_reports(load("s005"))
    report = repo.get(departments.KIND, departments.report_id("s005", today(), "quality"))
    assert set(report) - {"store_id", "id"} == {"dept", "date", "items", "order", "source"} and report["source"] == "code"
    assert report["order"] == [allergy["id"], umbrella["id"]]
    for p in (umbrella, allergy):  # 사원 검사를 통과한 것은 모두 남는다
        found = proposals.get(p["id"])
        assert found["state"] == "proposed" and "lead" not in found


def test_marketing_plan_is_reported_last():
    choongjang(at=None)
    seal = propose("customer", "negative_review", SEAL, "rv_x")
    plan_id = marketing.plan_id("s005", today())
    repo.put(marketing.KIND, plan_id, "s005", {"store_id": "s005", "date": today(), "menu_ids": ["m_1"],
                                               "angle": "x", "body": None, "hashtags": [], "lead": None})
    reports = departments.run_reports(load("s005"))
    assert [r["dept"] for r in reports] == ["customer", "marketing"]
    assert seal["id"] in reports[0]["items"] and reports[1]["items"] == [plan_id]


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


def test_why_lines():
    choongjang(at=None)
    p = propose("quality", "field_variable", UMBRELLA)
    assert staff_tasks._why(load("s005"), p, clock.now()) == "오늘 14시부터 비가 와요."
