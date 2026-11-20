"""알바생 할 일 제안 (voice/proposals.py, 에이전트 조직 개편 1단계).

아쉬운 리뷰 교정 카드는 제안(묻는 중)으로 남았다가, 사장님이 "진행해" 해야 할 일로 들어간다.
"""

from voice import proposals, repo, staff
from voice.tests.conftest import choongjang


def leak():
    donna = choongjang()
    donna.clock("2026-11-17T15:40:00+09:00")
    rid = donna.demo_review("leak")
    return donna, rid


def proposal_of(rid: str) -> dict:
    return proposals.get(repo.get("alert", f"al_{rid}")["proposal_id"])


def test_alert_leaves_an_asked_proposal_not_a_task():
    donna, rid = leak()
    found = proposal_of(rid)
    assert (found["state"], found["dept"], found["by"], found["task_id"]) == ("asked", "customer", "negative_review", None)
    assert found["payload"]["title"] == "배달 용기 이중 실링" and found["payload"]["must_confirm"] is True
    assert found["payload"]["urgent"] is False and found["payload"]["days"] == 2
    assert [t for t in staff.store_tasks("s005") if t["origin"] == "review"] == []  # 묻기만 했다


def test_approve_applies_with_source():
    donna, rid = leak()
    donna.open_notice()
    donna.turn("응, 진행해")
    found = proposal_of(rid)
    assert found["state"] == "applied" and found["decided_by"] == "owner_yes"
    [task] = [t for t in staff.store_tasks("s005") if t["id"] == found["task_id"]]
    assert task["origin"] == "review" and task["must_confirm"] is True and task["urgent"] is False
    source = task["source"]
    assert (source["by"], source["dept"], source["proposal_id"]) == ("negative_review", "customer", found["id"])
    assert source["alert_id"] == f"al_{rid}" and source["reason"] == {"type": "review", "review_id": rid}


def test_apply_twice_makes_one_task():
    donna, rid = leak()
    pid = proposal_of(rid)["id"]
    first = proposals.apply(pid, "test")
    again = proposals.apply(pid, "test")
    assert first["id"] == again["id"]
    assert len([t for t in staff.store_tasks("s005") if t["origin"] == "review"]) == 1


def test_no_card_declines():
    donna, rid = leak()
    donna.open_notice()
    donna.turn("카드는 넣지 마")
    donna.turn("응, 올려")
    found = proposal_of(rid)
    assert found["state"] == "declined" and found["task_id"] is None
    assert [t for t in staff.store_tasks("s005") if t["origin"] == "review"] == []


def test_two_stores_keep_their_own_documents():
    """가게마다 1번부터 매기는 번호라도 id 에 가게가 들어가 다른 가게 것을 덮어쓰거나 막지 않는다 (known-bugs B1)."""
    from voice import notices

    payload = {"title": "우산꽂이 내놓기", "detail": "입구에 우산꽂이를 내놓아 주세요", "phase": "open"}
    for store_id, name in (("s005", "민수"), ("s777", "지은")):
        proposals.create(store_id, dept="customer", by="field_variable", payload=payload, reason={"type": "weather"}, dedupe=False)
        notices.push(store_id, "negative_review", "아쉬운 리뷰가 올라왔어요")
        staff.ensure_person(store_id, name)
        staff.add_task(store_id, "바닥 닦기", "open", origin="owner")  # 예전에는 두 번째 가게에서 IntegrityError
    for store_id, name in (("s005", "민수"), ("s777", "지은")):
        assert len(repo.all_of("proposal", store_id)) == 1 and len(repo.all_of("notice", store_id)) == 1
        assert staff.find_by_name(store_id, name)["store_id"] == store_id
        assert [t["title"] for t in staff.store_tasks(store_id)] == ["바닥 닦기"]
