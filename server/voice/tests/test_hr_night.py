"""밤 9시 인사과 보고 (jobs/hr_night.py, Figma v0.2.1 J '영상 v15' K-01 승진 신청 · K-02 대리가 됐어요).

앞쪽은 승진 후보 고르기(규칙)를 가게 없이 인사과 기록만으로 본다 (가게 id s9 ~).
뒤쪽은 초옹장 H 픽스처(11/17 09:02, 포스터 사원, 지난 결재 19 승인 + 1 수정)로 아침 브리핑 → 밤 9시 → 승진까지 본다.
"""

import datetime as dt

import pytest

from voice import clock, config, hr, repo, width
from voice.clock import SEOUL
from voice.instagram import story_event
from voice.jobs import briefing, hr_night
from voice.tests.conftest import Choongjang, FakeGraph, hr_log, step_key
from voice.tests.test_instagram import connect

DAY = dt.date(2026, 11, 17)
START = dt.datetime(2026, 11, 1, 12, 0, tzinfo=SEOUL)
SE_ID = "se_s005_2026-11-17"


def decide_many(store: str, job: str, *reactions: str, start: dt.datetime = START) -> None:
    """결재 반응을 한 시간 간격으로 남긴다 (ref 는 건마다 다르게)."""
    done = len(hr.events(store, job))
    for n, reaction in enumerate(reactions):
        with clock.at(start + dt.timedelta(hours=done + n)):
            hr.record(store, job, f"{job}_{done + n}", reaction)


# ── 1. 승진 후보 (규칙) ──


def test_candidate_needs_minimum_decisions():
    hr.set_ranks("s9", {"story_poster": "staff"})
    decide_many("s9", "story_poster", *["approved"] * 4)
    assert hr_night.candidate("s9", DAY) is None  # 포스터 최소 5건
    decide_many("s9", "story_poster", "approved")
    # 혜택 포스터 상한(사원)은 보지 않는다: 사장님이 허락하면 대리까지 (owner_ok)
    assert hr_night.candidate("s9", DAY) == {"job": "story_poster", "from": "staff", "to": "assistant", "recent": 5, "approved": 5,
                                              "canceled": 0, "last_at": "2026-11-01T16:00:00+09:00"}


def test_candidate_needs_90_percent_as_is():
    hr.set_ranks("s9", {"story_poster": "staff"})
    decide_many("s9", "story_poster", *["approved"] * 9, "edited")
    assert hr_night.candidate("s9", DAY)["approved"] == 9  # 9/10 = 90% 는 된다
    hr.set_ranks("s10", {"story_poster": "staff"})
    decide_many("s10", "story_poster", *["approved"] * 8, "rejected", "edited")
    assert hr_night.candidate("s10", DAY) is None  # 80%


def test_candidate_counts_only_the_last_20():
    hr.set_ranks("s9", {"positive_reply": "staff"})
    decide_many("s9", "positive_reply", *["rejected"] * 5, *["approved"] * 20)
    found = hr_night.candidate("s9", DAY)
    assert (found["job"], found["recent"], found["approved"]) == ("positive_reply", 20, 20)


def test_canceled_after_blocks_promotion():
    hr.set_ranks("s9", {"story_poster": "staff"})
    decide_many("s9", "story_poster", *["approved"] * 10)
    with clock.at(START + dt.timedelta(days=2)):
        hr.record("s9", "story_poster", "story_poster_3", "canceled_after")
    assert hr_night.candidate("s9", DAY) is None


def test_only_asking_ranks_below_the_job_cap():
    hr.set_ranks("s9", {"review_fix_task": "staff", "positive_reply": "assistant"})
    decide_many("s9", "review_fix_task", *["approved"] * 10)  # 알바생 할 일은 사원이 상한
    decide_many("s9", "positive_reply", *["approved"] * 20)  # 대리는 묻지 않는 직급이라 후보가 아니다
    assert hr_night.candidate("s9", DAY) is None
    hr.set_ranks("s9", {"review_fix_task": "intern"})
    assert hr_night.candidate("s9", DAY)["to"] == "staff"


def test_picks_the_job_with_most_decisions_then_the_latest():
    hr.set_ranks("s9", {"story_poster": "staff", "field_task": "intern"})
    decide_many("s9", "story_poster", *["approved"] * 10)
    decide_many("s9", "field_task", *["approved"] * 5, start=START + dt.timedelta(days=5))  # 더 최근이지만 결재 수가 적다
    assert hr_night.candidate("s9", DAY)["job"] == "story_poster"

    hr.set_ranks("s10", {"field_task": "intern", "manual_task": "intern"})
    decide_many("s10", "field_task", *["approved"] * 5)
    decide_many("s10", "manual_task", *["approved"] * 5, start=START + dt.timedelta(days=1))  # 같은 수면 최근에 결재한 것
    assert hr_night.candidate("s10", DAY)["job"] == "manual_task"


def test_not_asked_again_for_seven_days():
    hr.set_ranks("s9", {"story_poster": "staff"})
    decide_many("s9", "story_poster", *["approved"] * 5)
    repo.put(hr_night.ASK_KIND, "s9:story_poster", "s9", {"store_id": "s9", "job": "story_poster", "date": DAY.isoformat(),
                                                           "candidate": {}, "answer": "no"})
    assert hr_night.candidate("s9", DAY + dt.timedelta(days=6)) is None
    assert hr_night.candidate("s9", DAY + dt.timedelta(days=7))["job"] == "story_poster"


# ── 2. 사장님이 허락한 승진 (hr.promote_by_owner) ──


def test_owner_promotion_lifts_the_offer_cap():
    hr.set_ranks("s9", {"story_poster": "assistant"})
    assert hr.rank("s9", "story_poster", offer=True) == "staff"  # 혜택 포스터는 평가로 올라도 사원까지
    assert hr.asks("s9", "story_poster", offer=True) == "batch"

    hr.set_ranks("s9", {"story_poster": "staff"})
    promoted = hr.promote_by_owner("s9", "story_poster", "assistant")
    assert (promoted["rank"], promoted["changed_by"], promoted["owner_ok"]) == ("assistant", "owner", True)
    assert promoted["history"][-1]["by"] == "owner"
    assert hr.rank("s9", "story_poster", offer=True) == "assistant" and hr.asks("s9", "story_poster", offer=True) is None
    with pytest.raises(ValueError):
        hr.promote_by_owner("s9", "review_fix_task", "assistant")  # 업무 상한(사원)은 넘지 않는다


# ── 3. 초옹장 H: 아침 브리핑 → 밤 9시 (시연 장면) → 승진 ──


@pytest.fixture
def h(monkeypatch, ig_on) -> Choongjang:
    monkeypatch.setattr(config, "DEMO_FIXTURE", "s005_choongjang")  # connect 를 {} 로 부르면 이 가게
    ig_on(FakeGraph())
    donna = Choongjang()
    assert donna.client.post("/v1/dev/fixtures", json={"fixture": "s005_choongjang_h"}).json()["store_id"] == "s005"
    connect(donna)
    return donna


def listen_to_the_end(donna: Choongjang) -> dict:
    """묻는 것에는 모두 "응"하며 아침 브리핑을 끝까지 듣는다."""
    response = donna.turn("오늘 일정 브리핑해 줘")
    for _ in range(20):
        if response["type"] == "end":
            return response
        asks = step_key(response) == "detail_ask" or response["expects_reply"]
        response = donna.turn("응") if asks else donna.turn(event="auto_next")
    raise AssertionError("브리핑 끝에 닿지 못했어요")


def test_h_morning_then_night_promotion(h: Choongjang):
    end = listen_to_the_end(h)
    # 시연: 끝 화면을 보여 준 뒤 밤 9시 장면으로 (시계를 멈춘 픽스처 가게, 밤에 물을 승진이 있다)
    assert end["next_scene"] == {"event": "night_hr", "after_ms": hr_night.SCENE_AFTER_MS}
    assert ("비 오는 날 이벤트 스토리", "9:02에 스토리에 올렸어요") in [(r["value"], r["sub"]) for r in end["cards"][0]["rows"]]

    k01 = h.turn(event="night_hr")
    assert clock.now().isoformat() == "2026-11-17T21:00:00+09:00" and k01["clock_moved"] is True
    assert (k01["type"], k01["ask"], k01["expects_reply"], k01["briefing"]) == ("ask", {"key": "promotion"}, True, None)
    assert k01["headline"] == "스토리는 먼저 올리고\n저녁에 보고할까요?"
    assert [s["text"] for s in k01["say"]] == ["인사과 보고입니다.", "인스타 관리 담당이 대리 승진을 신청했어요.",
                                               "최근 20건 중 19건을 그대로 승인하셨고, 사후 취소는 없었어요.",
                                               "앞으로 스토리는 먼저 올리고 저녁에 보고할까요?"]
    assert [(r["id"], r["value"]) for r in k01["cards"][0]["rows"]] == [
        ("k_who", "인스타 관리 · 사원 → 대리"), ("k_ok", "최근 20건 중 19건 그대로 승인"), ("k_undo", "사후 취소 0번"),
        ("k_change", "먼저 올리고 저녁에 보고")]
    # 줄 카드 k_ok 는 rows.value 한도(14)를 0.5 넘는다 (Figma 문구 그대로라 고치지 않음, 보고서 참고). 제목·말은 한도 안
    assert [v for v in width.violations(k01) if not v.startswith("promotion.")] == []
    assert hr_night.KIND not in [n["kind"] for n in h.notices()]  # 바로 보고했으니 밤 9시 알림은 띄우지 않는다
    assert all(j["done"] for j in repo.all_of("job", "s005") if j["kind"] == hr_night.KIND)
    status = h.get("/v1/home")["store_status"]
    assert status == {"state": "closed", "label": "영업 끝", "detail": "저녁 8시 30분에 닫았어요"}

    k02 = h.turn("그래, 그렇게 해")
    assert k02["type"] == "answer" and k02["headline"] == "대리가 됐어요"
    assert [s["text"] for s in k02["say"]] == ["감사합니다."]  # 화면은 K-02, 말은 감사 인사만
    card = k02["cards"][0]
    assert card["note"] == "대리로 승진" and card["rows"][0]["value"] == "인스타 관리 · 대리"
    rank = hr.stored("s005", "story_poster")
    assert (rank["rank"], rank["changed_by"], rank["owner_ok"]) == ("assistant", "owner", True)
    assert hr.asks("s005", "story_poster", offer=True) is None  # 혜택 포스터도 이제 묻지 않는다
    assert repo.get(hr_night.ASK_KIND, "s005:story_poster")["answer"] == "yes"
    again = h.turn("응")
    assert again["headline"] != "대리가 됐어요" and hr.stored("s005", "story_poster")["history"][-1]["by"] == "owner"


def test_no_keeps_asking_and_waits_a_week(h: Choongjang):
    k01 = h.turn(event="night_hr")  # 브리핑을 듣지 않아도 시연 장면은 온다
    assert k01["ask"] == {"key": "promotion"}
    no = h.turn("아니")
    assert no["headline"] == "지금처럼 여쭤볼게요" and [s["text"] for s in no["say"]] == ["네, 지금처럼 여쭤보고 할게요."]
    assert hr.stored("s005", "story_poster")["rank"] == "staff"
    assert repo.get(hr_night.ASK_KIND, "s005:story_poster")["answer"] == "no"
    assert hr_night.candidate("s005", DAY)["job"] == "field_task"  # 포스터는 일주일 동안 다시 묻지 않는다 (현장 할 일 5/5 가 다음)
    assert hr_night.candidate("s005", DAY + dt.timedelta(days=7))["job"] == "story_poster"


def promoted_story_day(h: Choongjang) -> dict:
    """포스터를 사장님이 대리로 올려 둔 뒤 아침 준비: 밤사이 준비한 포스터를 묻지 않고 첫 식사 피크 한 시간 전에 올리기로 한다."""
    hr.promote_by_owner("s005", "story_poster", "assistant")
    briefing.prepare("s005")
    return story_event.get(SE_ID)


def test_story_auto_post_then_night_report(h: Choongjang):
    record = promoted_story_day(h)
    assert record["state"] == "approved" and record["auto"] is True
    [post] = repo.all_of("instagram_post", "s005")
    assert (post["kind"], post["status"], post["post_at"]) == ("story", "queued", "2026-11-17T11:00:00+09:00")  # 점심 12시 한 시간 전
    brief = briefing.current("s005")
    assert brief["steps"]["story_event"] is None and "p_story" not in [r["id"] for r in brief["home_rows"]]  # 브리핑에서 묻지 않는다
    assert [(j["kind"], j["due_at"]) for j in repo.all_of("job", "s005") if j["kind"] == hr_night.KIND] == [
        ("hr_night", "2026-11-17T21:00:00+09:00")]

    h.clock("2026-11-17T11:00:00+09:00")
    assert repo.get("instagram_post", post["id"])["status"] == "published"
    assert hr_log() == [("story_poster", "done")]  # 묻지 않고 올린 것은 done

    h.clock("2026-11-17T21:00:00+09:00")
    [notice] = [n for n in h.notices() if n["kind"] == hr_night.KIND]
    assert notice["opens_turn"] is True and notice["text"] == "인사과 보고가 있어요" and notice["alert_id"] == "s005:2026-11-17"
    night = h.turn(event="notice", notice_id=notice["id"])
    assert [s["text"] for s in night["say"]][:2] == ["인사과 보고입니다.", "인스타 스토리에 이벤트 포스터를 먼저 올렸어요."]
    # 포스터는 이미 대리라 다음 후보(현장 할 일 인턴 5/5)를 묻는다. 사원 질문은 제목 두 줄로
    assert night["ask"] == {"key": "promotion"} and night["headline"] == "현장 할 일은 묶어서\n한 번에 여쭤볼까요?"
    assert [v for v in width.violations(night) if not v.startswith("promotion.")] == []
    [done] = [e for e in hr.events("s005", "story_poster") if e["reaction"] == "done"]
    assert done["reported_at"] == "2026-11-17T21:00:00+09:00"  # 보고를 앱에 보냈다
    assert hr_night.done_today("s005", DAY) == []

    yes = h.turn("응, 그렇게 해")
    assert yes["headline"] == "사원이 됐어요" and hr.rank("s005", "field_task") == "staff"


def test_unheard_night_report_goes_to_next_morning_done_report(h: Choongjang):
    promoted_story_day(h)
    h.clock("2026-11-17T11:00:00+09:00")  # 올라간다 (done)
    h.clock("2026-11-18T09:30:00+09:00")  # 밤 9시 알림은 열지 않았다. 다음 날 아침 준비
    step = briefing.current("s005")["steps"]["done_report"]
    assert "인스타 스토리에 이벤트 포스터를 올렸어요." in [s["text"] for s in step["say"]]
    assert ("이벤트 스토리", "1건") in [(r["label"], r["value"]) for r in step["cards"][0]["rows"]]
    assert width.violations(step) == []
