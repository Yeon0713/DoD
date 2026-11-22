"""사후 보고와 사후 취소 (인사과 9장 5단계, voice/jobs/done_report.py, 4-6·4-7)."""

import datetime as dt

from voice import clock, hr, repo
from voice.clock import SEOUL
from voice.jobs import briefing, done_report
from voice.tests.conftest import FakeGraph, hr_log, walk_to
from voice.tests.test_instagram import Choongjang, chj, connect  # noqa: F401 (chj 는 fixture)
from voice.tests.test_scenario_b import night_then_morning


def to_report(donna) -> dict:
    """밤사이 바로 단 사과 답글을 알리는 단계(H-10 negative_done)까지 듣는다. 앱에 보내면 보고한 것으로 적는다."""
    return walk_to(donna, "negative_done")


def test_assistant_done_reported_then_undone_and_demoted():
    donna, rid = night_then_morning()
    report = to_report(donna)
    assert report["briefing"]["step_key"] == "negative_done"
    [event] = [e for e in hr.events("s001") if e["reaction"] == "done"]
    assert event["reported_at"] == "2026-11-17T09:00:00+09:00"  # 앱에 보낸 때 (9-0 h)
    undone = donna.turn("그 답글 지워")
    assert undone["intent"] == "report.undo" and [s["text"] for s in undone["say"]] == ["배달이 늦어 음식이 식었다는 리뷰에 단 답글을 지웠어요."]
    review = repo.review(rid)
    assert review["reply_status"] == "none" and review["reply_deleted_at"] and review["reply_deleted_text"].startswith("늦은 배달로")
    assert hr.rank("s001", "negative_reply") == "staff"  # 사후 취소 1건이면 바로 한 단계 (말하지 않는다)
    assert hr_log("s001") == [("negative_reply", "done"), ("negative_reply", "canceled_after")]
    assert all("직급" not in s["text"] and "강등" not in s["text"] for s in undone["say"])
    briefing.prepare("s001")  # 지운 답글은 다시 쓰거나 묻지 않는다
    assert "reply_ready" not in repo.review(rid) or repo.review(rid)["reply_status"] == "none"
    assert {"job": "negative_reply", "ref": rid} not in ((briefing.current("s001")["steps"].get("negative") or {}).get("action") or {}).get("items", [])


def test_undo_after_closing_deletes_but_does_not_demote():
    donna, rid = night_then_morning()
    to_report(donna)
    donna.clock("2026-11-17T22:30:00+09:00")  # 문 닫은 뒤 (22:00)
    donna.turn("그 답글 지워")
    assert repo.review(rid)["reply_status"] == "none"  # 지우기는 한다
    assert hr.rank("s001", "negative_reply") == "assistant" and ("negative_reply", "canceled_after") not in hr_log("s001")


def test_unheard_report_carries_to_the_next_one():
    donna, rid = night_then_morning()  # 11/17 브리핑을 듣지 않았다
    donna.clock("2026-11-18T09:00:00+09:00")
    step = briefing.current("s001")["steps"]["done_report"]
    assert step and "아쉬운 리뷰 한 개에 사과 답글을 올렸어요." in [s["text"] for s in step["say"]]


def test_manager_count_is_reported_on_monday():
    hr.set_ranks("s9", {"positive_reply": "manager"})
    with clock.at(dt.datetime(2026, 11, 26, 11, 0, tzinfo=SEOUL)):  # 목요일
        for n in range(3):
            hr.record("s9", "positive_reply", f"rv_{n}", "done")
    assert hr.report_items("s9", dt.datetime(2026, 11, 28, 9, 0, tzinfo=SEOUL)) == []  # 토요일: 아직
    monday = hr.report_items("s9", dt.datetime(2026, 11, 30, 9, 0, tzinfo=SEOUL))
    assert len(monday) == 3 and {e["rank_at"] for e in monday} == {"manager"}


def test_ordinal_picks_from_todays_report_and_unclear_asks():
    donna, _ = night_then_morning()
    to_report(donna)
    asked = donna.turn("세 번째 거 지워")  # 한 건뿐이다
    assert asked["intent"] == "report.undo" and asked["headline"] == "어느 것을 지울까요?" and asked["expects_reply"] is True


def test_staff_cancel_words_are_not_taken():
    from voice.dialog import intent_rules

    assert intent_rules.match("그거 취소해", None).name == "staff.cancel"  # D-33 알바생 일 취소는 그대로
    assert intent_rules.match("두 번째 할 일 취소해", None).name != "report.undo"
    assert intent_rules.match("어제 인스타 지워", None).name == "report.undo"


def test_instagram_undo_deletes_on_graph(chj: Choongjang, ig_on):
    fake = ig_on(FakeGraph())
    connect(chj)
    chj.client.post("/v1/dev/hr", json={"store_id": "s005", "ranks": {"instagram_post": "assistant"}})
    briefing.prepare("s005")
    chj.clock("2026-11-17T11:00:00+09:00")  # 올라간다 (done)
    chj.clock("2026-11-18T09:30:00+09:00")  # 다음 날 준비
    step = briefing.current("s005")["steps"]["done_report"]
    assert "인스타에 게시물을 올렸어요." in [s["text"] for s in step["say"]]
    chj.session_id = "sess_ig"
    assert walk_to(chj, "done_report")["briefing"]["step_key"] == "done_report"
    undone = chj.turn("어제 인스타 지워")
    assert undone["headline"] == "지웠어요" and "DELETE" in [m for m, _, _ in fake.calls]
    statuses = sorted(p["status"] for p in repo.all_of("instagram_post", "s005") if p["kind"] == "feed")
    assert statuses == ["deleted", "queued"]  # 어제 것은 지우고, 오늘 것은 그대로 (대리였을 때 준비)
    assert hr.rank("s005", "instagram_post") == "staff"
