"""같은 할 일 묶기와 반복 → 매뉴얼 (voice/proposals.py, 에이전트 조직 개편 2단계)."""

import pytest

from Harness.tests.fakes import FakeClova, call
from voice import config, proposals, staff, staff_db
from voice.similar import dice
from voice.tests.conftest import choongjang

SEAL = {"title": "배달 용기 이중 실링", "detail": "국물 메뉴는 랩을 두 번 씌우고 뚜껑에 테이프를 한 번 더 붙여 주세요",
        "phase": "open", "days": 2, "must_confirm": True, "urgent": False}
SEAL_AGAIN = {**SEAL, "title": "국물 용기 이중 실링", "detail": "국물 메뉴는 랩을 두 번 씌우고 뚜껑을 테이프로 한 번 더 붙여 주세요"}
UMBRELLA = {**SEAL, "title": "우산꽂이 내놓기", "detail": "입구에 우산꽂이를 내놓아 주세요"}


@pytest.fixture
def same_on(clova_on, monkeypatch):
    """같은 일 질문(agents/same_task)만 켠다. 브리핑 준비 같은 다른 에이전트는 꺼 둔다."""
    monkeypatch.setattr(config, "agent_on", lambda name: name == "same")
    return clova_on


def propose(payload: dict, review_id: str) -> dict:
    return proposals.create("s005", dept="customer", by="negative_review", payload=payload,
                            reason={"type": "review", "review_id": review_id}, link={"type": "review", "review_id": review_id})


def applied(payload: dict, review_id: str) -> dict:
    return proposals.apply(propose(payload, review_id)["id"], "test")


def test_dice():
    assert dice("배달 용기 이중 실링", "배달 용기 이중 실링") == 1.0
    assert dice(SEAL["title"] + SEAL["detail"], SEAL_AGAIN["title"] + SEAL_AGAIN["detail"]) >= proposals.SAME_SCORE
    assert dice(SEAL["title"] + SEAL["detail"], UMBRELLA["title"] + UMBRELLA["detail"]) < proposals.SAME_SCORE


def test_same_review_merges_without_llm():
    choongjang()
    task = applied(SEAL, "rv_a")
    again = propose(UMBRELLA, "rv_a")  # 같은 리뷰에서 다시 나온 제안 (글이 달라도)
    assert again["state"] == "merged" and again["same_as"] == task["id"]
    assert [m["proposal_id"] for m in staff_db.task(task["id"])["source"]["merged"]] == [again["id"]]


def test_similar_but_agent_off_adds_new():
    """LLM 을 부를 수 없으면 묶지 않는다 (교정이 사라지는 것보다 하나 더 뜨는 편이 낫다)."""
    choongjang()
    applied(SEAL, "rv_a")
    assert propose(SEAL_AGAIN, "rv_b")["state"] == "proposed"


def test_similar_and_llm_says_same(same_on):
    choongjang()
    task = applied(SEAL, "rv_a")
    fake = same_on(FakeClova([call("submit_same", {"same_as": task["id"], "reason": "같은 실링"})]))
    again = propose(SEAL_AGAIN, "rv_b")
    assert again["state"] == "merged" and again["same_as"] == task["id"] and fake.done()


def test_not_similar_never_asks_llm(same_on):
    choongjang()
    applied(SEAL, "rv_a")
    fake = same_on(FakeClova())  # 부르면 실패한다
    assert propose(UMBRELLA, "rv_b")["state"] == "proposed" and fake.requests == []


def test_urgent_is_not_merged_into_plain():
    choongjang()
    applied(SEAL, "rv_a")
    urgent = proposals.create("s005", dept="quality", by="negative_review", payload={**SEAL, "urgent": True},
                              reason={"type": "review", "review_id": "rv_a"}, link={"review_id": "rv_a"})
    assert urgent["state"] == "proposed"


def test_today_impact_is_not_merged_into_plain():
    """현장 변수의 today_impact 도 긴급이다. 같은 글의 일반 할 일에 묶이면 긴급 표시가 사라진다 (known-bugs B2)."""
    choongjang()
    applied(UMBRELLA, "rv_a")
    impact = proposals.create("s005", dept="customer", by="field_variable", payload={**UMBRELLA, "today_impact": True},
                              reason={"type": "weather"})
    assert impact["state"] == "proposed" and proposals.urgent(impact)


def test_three_in_a_week_proposes_manual_once():
    donna = choongjang()
    task = applied(SEAL, "rv_a")
    propose(SEAL, "rv_a")  # 같은 리뷰 → 묶임 (2번째)
    assert proposals.promote_repeats("s005") == []
    propose(UMBRELLA, "rv_a")  # 같은 리뷰 → 묶임 (3번째)
    [made] = proposals.promote_repeats("s005")
    assert (made["by"], made["dept"], made["payload"]["repeat"], made["reason"]) == (
        "manual_coach", "quality", "daily", {"type": "repeat", "task_id": task["id"], "count": 3})
    assert made["payload"]["title"] == SEAL["title"]  # 에이전트를 끄면 첫 할 일 제목 그대로
    assert proposals.promote_repeats("s005") == []  # 한 번만

    daily = proposals.apply(made["id"], "owner_yes")
    assert daily["repeat"] == "daily" and daily["origin"] == "manual" and daily["source"]["by"] == "manual_coach"
    assert staff_db.task(task["id"])["source"]["promoted_at"]
    donna.clock("2026-11-18T11:00:00+09:00")
    assert SEAL["title"] in [t["title"] for t in staff.store_tasks("s005") if t["repeat"] == "daily"]


def test_older_than_a_week_is_not_counted():
    donna = choongjang()
    applied(SEAL, "rv_a")
    propose(SEAL, "rv_a")
    propose(SEAL, "rv_a")
    donna.clock("2026-11-25T11:00:00+09:00")  # 8일 뒤
    assert proposals.promote_repeats("s005") == []


def test_manual_line_rejects_new_actions(clova_on, monkeypatch):
    """매뉴얼 한 줄을 다듬을 때 반복된 할 일에 없는 행동(새 용기 사기)을 더하면 거절하고 다시 쓰게 한다."""
    monkeypatch.setattr(config, "agent_on", lambda name: name == "manual")
    choongjang()
    applied(SEAL, "rv_a")
    propose(SEAL, "rv_a")
    propose(SEAL, "rv_a")
    fake = clova_on(FakeClova(
        [call("submit_manual", {"title": "새 포장 용기 주문", "detail": "누수 없는 용기를 새로 주문해 주세요"})],
        [call("submit_manual", {"title": "국물 포장 이중 실링", "detail": "국물 메뉴는 랩을 두 번 씌우고 뚜껑에 테이프를 한 번 더 붙여요"})],
        *[[call("submit_judgement", {"found": True, "quotes": ["같음"]})]] * 2,  # 2차 감사(감사팀): 행동 둘이 반복된 할 일에 있나
    ))
    [made] = proposals.promote_repeats("s005")
    assert made["payload"]["title"] == "국물 포장 이중 실링" and fake.done()
    assert "새 행동을 더하지 마세요" in fake.tool_messages(1)[0]


def test_stale_asked_proposal_is_not_a_candidate():
    """영업 중 알림에서 물었다가(asked, 물을 날 없음) 2시간이 지난 제안은 끝난 것이다. 같은 일로 묶지 않는다 (2026-11-22 버그 V2)."""
    donna = choongjang()
    donna.clock("2026-11-17T16:00:00+09:00")
    old = proposals.create("s005", dept="customer", by="negative_review", payload=SEAL, state="asked",
                           reason={"type": "review", "review_id": "rv_a"}, link={"type": "review", "review_id": "rv_a"})
    donna.clock("2026-11-17T17:00:00+09:00")
    assert propose(SEAL, "rv_b")["state"] == "merged"  # 2시간 안이면 아직 묻는 중일 수 있다
    donna.clock("2026-11-17T18:30:00+09:00")
    fresh = propose(SEAL, "rv_c")
    assert fresh["state"] == "proposed" and proposals.get(old["id"])["state"] == "asked"
