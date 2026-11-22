"""감사팀 6단계: 끝내 불합격한 결과를 직급대로 처리한다 (감사팀 계획 8-3~8-5, 결정 7·8·12).

대리·과장 건은 보류(hold): 올리지 않고 걸린 초안 그대로 그 건만 묻는다. 인사과 기록은 남기지 않는다.
인턴·사원 건은 템플릿으로 물러나 묻는다. 감사 자체는 test_audit_moved·test_audit_criteria 가 보고, 여기서는 담당 입구의
감사 결과(audit.passed)를 정해 두고 부르는 곳의 흐름만 본다.
"""

import pytest

from voice import clock, config, hr, marketing, repo
from voice.agents import caption_writer, topic_finder, voice_reply
from voice.audit import log as audit_log
from voice.context import load
from voice.jobs import auto_reply, briefing, cause
from voice.tests.conftest import FakeGraph, choongjang, hr_log
from voice.tests.test_instagram import chj, connect  # noqa: F401 (chj 는 fixture)

BAD = "국물이 새서 정말 죄송합니다. 포장할 때 더 꼼꼼히 살피겠습니다."
FAILED, PASSED = {"passed": False, "rounds": 2}, {"passed": True, "rounds": 0}


@pytest.fixture
def written(monkeypatch):
    """답글 담당의 결과를 정해 둔다. fail 에 든 리뷰 id 는 끝내 불합격, 나머지는 합격."""
    def use(fail=None):
        def fake(view, review, kind, occasion=None, fix=None):
            bad = fail is None or review["id"] in fail
            return {"text": BAD, "source": "AGENT", "notes": [], "audit": FAILED if bad else PASSED}

        monkeypatch.setattr(voice_reply, "write", fake)
        monkeypatch.setattr(config, "ALERT_AGENT_REPLY", True)  # 알림 답글도 답글 담당이 쓰는 길

    return use


def test_assistant_live_negative_is_held_and_asked(written):
    """① 대리 가게 영업 중 부정 리뷰, 답글 끝내 불합격 → 올리지 않고 알림, 걸린 초안을 묻고, 승인해도 인사과 기록 없음."""
    donna = choongjang(permission=True)
    donna.clock("2026-11-17T15:40:00+09:00")
    written()
    rid = donna.demo_review("leak")
    record = repo.get("alert", f"al_{rid}")
    assert record["state"] == "alerted" and record["audit_hold"] is True and record["reply_base"] == BAD
    assert repo.review(rid)["reply_status"] == "proposed" and repo.review(rid)["audit_hold"] is True
    jobs = {j["kind"] for j in donna.state()["job"] if j["payload"].get("review_id") == rid}
    assert {"review_remind", "review_fallback"} <= jobs  # 인턴처럼 다시 알림과 25분 대체 작업
    asked = donna.open_notice()
    assert asked["cards"][0]["reply"]["text"].startswith(BAD)  # 걸린 초안 그대로 (결정 12)
    donna.turn("응, 진행해")
    assert repo.review(rid)["reply_status"] == "posted"
    assert ("negative_reply", "approved") not in hr_log() and ("negative_reply", "done") not in hr_log()


def test_assistant_passed_posts_without_asking(written):
    """합격이면 지금처럼 대리는 묻지 않고 올리고 인사과에 done."""
    donna = choongjang(permission=True)
    donna.clock("2026-11-17T15:40:00+09:00")
    written(fail=set())
    rid = donna.demo_review("leak")
    assert repo.review(rid)["reply_status"] == "posted" and not repo.review(rid)["audit_hold"]
    assert ("negative_reply", "done") in hr_log()


def test_assistant_after_hours_is_asked_in_the_morning(written):
    """② 같은 가게 문 닫은 뒤 → 바로 답하기가 올리지 않고, 아침 브리핑 아쉬운 리뷰 단계에 나온다."""
    donna = choongjang(permission=True)
    donna.clock("2026-11-17T21:00:00+09:00")
    written()
    rid = donna.demo_review("leak")
    with clock.at(clock.now() + config.AUTO_REPLY_DELAY):
        assert auto_reply.reply_now("s005", rid) is None
    found = repo.review(rid)
    assert found["reply_status"] == "none" and found["audit_hold"] is True and found["reply_ready"]["text"] == BAD
    donna.clock("2026-11-18T09:30:00+09:00")
    briefing.prepare("s005")
    step = briefing.current("s005")["steps"]["negative"]
    assert step is not None and rid in [i["ref"] for i in step["action"]["items"]]
    assert audit_log.rows_of("s005") == []  # 담당을 가짜로 바꿔 감사 기록은 없다 (기록은 test_audit_moved)


def test_manager_positive_holds_only_the_failed_one(written):
    """③ 과장 가게 칭찬 답글 불합격 → 예약 답글 단계에서 그 건만 묻고 나머지는 예약."""
    choongjang(at=None)
    hr._start("s005", "positive_reply", "manager")
    positives = [r for r in repo.reviews("s005") if r.get("sentiment") == "positive"][:2]
    for r in positives:
        repo.save_review({**r, "reply_status": "none"})
    bad, good = positives[0]["id"], positives[1]["id"]
    written(fail={bad})
    briefing.schedule_replies(load("s005"), clock.now())
    assert repo.review(bad)["reply_status"] == "awaiting" and repo.review(bad)["audit_hold"] is True
    assert repo.review(good)["reply_status"] == "scheduled" and repo.review(good)["reply_trigger"] == "auto"
    asked, _ = briefing.step_scheduling(load("s005"), clock.now())
    assert [i["ref"] for i in asked["action"]["items"]] == [bad]


def test_intern_failed_reply_falls_back_to_template(written):
    """④ 인턴 가게 불합격 → 템플릿 답글로 묻는다."""
    donna = choongjang()
    donna.clock("2026-11-17T15:40:00+09:00")
    written()
    rid = donna.demo_review("leak")
    record = repo.get("alert", f"al_{rid}")
    assert record["reply_base"] == cause.DETAILS["leak"]["reply"] and record["reply_source"] == "TEMPLATE"
    assert record["audit_hold"] is False


def test_intern_night_draft_is_template(written):
    choongjang(at=None)
    rid = "rv_0412"
    review = repo.review(rid)
    repo.save_review({**review, "reply_ready": None, "reply_status": "none"})
    written()
    briefing.draft_negative(load("s005"))
    ready = repo.review(rid)["reply_ready"]
    assert ready["source"] == "TEMPLATE" and ready["text"] != BAD and not repo.review(rid)["audit_hold"]


def test_assistant_instagram_is_held(chj, ig_on, monkeypatch):  # noqa: F811
    """⑥ 대리 인스타 불합격 → 게시 예약 없음, 인스타 단계에서 묻기. 승인해도 인사과 기록 없음."""
    ig_on(FakeGraph())
    connect(chj)
    hr._start("s005", "instagram_post", "assistant")
    monkeypatch.setattr(topic_finder, "suggest", lambda view: {"menu_ids": ["m_1", "m_2", "m_3"], "angle": "추운 날 국물", "audit": FAILED})
    monkeypatch.setattr(caption_writer, "write", lambda *a, **k: {"body": "따뜻한 국물 한 그릇 하세요. 들깨 향이 좋아요.", "hashtags": [],
                                                                "audit": PASSED})
    view = load("s005")
    plan = marketing.plan_today(view)
    assert plan["audit_hold"] is True
    assert briefing.auto_instagram(load("s005"), clock.now()) is None
    response, _ = briefing.step_instagram(load("s005"))
    assert response is not None and response["ask"]["key"] == "instagram_post"
    assert hr.record("s005", "instagram_post", f"instagram:s005:{view.now.date().isoformat()}", "approved") is None


def test_intern_instagram_topic_failure_keeps_rule_feed(chj, ig_on, monkeypatch):  # noqa: F811
    ig_on(FakeGraph())
    connect(chj)
    monkeypatch.setattr(topic_finder, "suggest", lambda view: {"menu_ids": ["m_1"], "angle": "x", "audit": FAILED})
    assert marketing.plan_today(load("s005")) is None  # 계획 없음 → 지금 규칙(많이 나간 메뉴)
