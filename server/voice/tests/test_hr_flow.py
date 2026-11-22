"""직급대로 동작 (인사과 9장 4단계, donna-voice/docs/agent-structure.md 4-1·9-0).

4-a 부정 리뷰 답글은 test_loop_negative(A 묶음), test_scenario_a·b, test_v021_choongjang 에서 본다.
"""

from voice import clock, hr, repo
from voice.instagram import posts
from voice.jobs import briefing
from voice.tests.conftest import FakeGraph, baseline, hr_log, prepared
from voice.tests.test_instagram import Choongjang, chj, connect, no_story_event, run_publish  # noqa: F401 (chj 는 fixture)


# ── 4-b 칭찬 리뷰 답글 ──


def test_manager_schedules_without_asking_and_records_done_when_posted():
    donna = prepared()  # 기준 가게(s001): 칭찬 답글 과장
    assert {r["reply_trigger"] for r in repo.reviews("s001") if r.get("reply_status") == "scheduled"} == {"auto"}
    assert repo.get("briefing", "s001:2026-11-17")["steps"]["scheduling"] is None  # 예약 답글 단계를 보이지 않는다 (9-0 c)
    donna.clock("2026-11-17T11:00:00+09:00")
    assert hr_log("s001") == [("positive_reply", "done")]  # 일요일 리뷰 하나가 화요일 11시에 올라갔다


def test_intern_asks_each_positive_reply():
    payload = baseline()
    payload["hr"] = {**payload["hr"], "positive_reply": "intern"}
    donna = prepared(payload)
    assert {r["id"] for r in repo.reviews("s001") if r.get("reply_status") == "awaiting"} == {"rv_0408", "rv_0409", "rv_0410"}
    step = repo.get("briefing", "s001:2026-11-17")["steps"]["scheduling"]
    assert step["type"] == "ask_action" and step["action"]["mode"] == "each" and len(step["action"]["items"]) == 1
    assert step["say"][-1]["text"] == "이렇게 예약할까요?"
    assert [j for j in donna.state()["job"] if j["kind"] == "post_scheduled"] == []  # 묻기 전에는 예약하지 않는다


def test_unanswered_positive_reply_is_asked_again_next_morning(chj: Choongjang):
    """칭찬 답글 사원(s005): 대답이 없으면 올리지 않고, 다음 날 때와 글을 새로 정해 다시 묻는다 (9-0 b)."""
    before = {r["id"]: r["reply_post_at"] for r in repo.reviews("s005") if r.get("reply_status") == "awaiting"}
    assert set(before) == {"rv_0401", "rv_0405", "rv_0409"}
    chj.clock("2026-11-18T09:30:00+09:00")  # 다음 날 브리핑 준비
    after = {r["id"]: r for r in repo.reviews("s005") if r["id"] in before}
    assert all(r["reply_status"] == "awaiting" for r in after.values())
    assert after["rv_0405"]["reply_post_at"] != before["rv_0405"]  # 11/17 11시는 지났다
    assert after["rv_0409"]["reply_post_at"] == before["rv_0409"]  # 토요일은 아직
    assert briefing.current("s005")["steps"]["scheduling"]["type"] == "ask_action"


# ── 4-b 인스타 게시 ──


def test_assistant_posts_instagram_before_the_first_peak(chj: Choongjang, ig_on):
    fake = ig_on(FakeGraph())
    connect(chj)
    chj.client.post("/v1/dev/hr", json={"store_id": "s005", "ranks": {"instagram_post": "assistant"}})
    briefing.prepare("s005")
    [post] = [p for p in repo.all_of("instagram_post", "s005") if p["kind"] == "feed"]
    assert post["status"] == "queued" and post["auto"] is True and post["post_at"] == "2026-11-17T11:00:00+09:00"  # 점심 12시 한 시간 전
    assert briefing.current("s005")["steps"]["instagram"] is None  # 묻지 않는다
    run_publish(chj)
    assert fake.paths("POST") == []  # 아직 때가 아니다
    chj.clock("2026-11-17T11:00:00+09:00")
    assert posts.get(post["id"])["status"] == "published" and hr_log() == [("instagram_post", "done")]
    briefing.prepare("s005")
    assert len([p for p in repo.all_of("instagram_post", "s005") if p["kind"] == "feed"]) == 1  # 같은 날 두 번 올리지 않는다


def test_staff_instagram_is_asked_like_intern(chj: Choongjang, ig_on):
    ig_on(FakeGraph())
    no_story_event(chj)  # 비 오는 날 이벤트가 있는 날은 스토리만 묻는다
    connect(chj)
    chj.client.post("/v1/dev/hr", json={"store_id": "s005", "ranks": {"instagram_post": "staff"}})
    briefing.prepare("s005")
    assert briefing.current("s005")["steps"]["instagram"]["headline"] == "인스타에 올릴까요?"  # 하루 한 건이라 묶지 않는다 (9-0 e)
    assert hr.asks("s005", "instagram_post") == "batch" and clock.now().date().isoformat() == "2026-11-17"


# ── 4-c 영업 중 묶음 창, 알바생 할 일 인턴 ──


def staff_negative(rank: str = "staff"):
    from voice.tests.conftest import choongjang

    donna = choongjang()
    donna.client.post("/v1/dev/hr", json={"store_id": "s005", "ranks": {"negative_reply": rank}})
    donna.clock("2026-11-17T15:40:00+09:00")
    return donna, donna.demo_review("leak")


def test_staff_negative_waits_in_the_window_then_asks_once():
    donna, rid = staff_negative()
    assert repo.all_of("notice", "s005") == [] and repo.get("alert", f"al_{rid}")["state"] == "batched"
    assert repo.review(rid)["reply_status"] == "none"  # 묻기 전에는 올리지 않는다
    donna.clock("2026-11-17T16:09:00+09:00")
    assert repo.all_of("notice", "s005") == []
    donna.clock("2026-11-17T16:10:00+09:00")  # 첫 건 + 30분
    [notice] = repo.all_of("notice", "s005")
    assert notice["kind"] == "hr_batch" and notice["opens_turn"] is True and notice["text"] == "확인할 것이 두 개 있어요"
    asked = donna.open_notice()
    assert asked["type"] == "ask_action" and asked["headline"] == "이대로 할까요?" and asked["action"]["mode"] == "batch"
    assert [i["job"] for i in asked["action"]["items"]] == ["negative_reply", "review_fix_task"]
    assert [s["text"] for s in asked["say"]] == ["여쭤볼 게 두 개 있어요.", "첫째, 국물이 샜다는 리뷰예요.",
                                                "둘째, 알바생 할 일 배달 용기 이중 실링이에요.", "이대로 할까요?"]
    done = donna.turn("두 번째는 빼고 올려")
    assert [s["text"] for s in done["say"]] == ["사과 답글을 올렸어요.", "네, 알바생 할 일은 넣지 않을게요."]
    posted = repo.review(rid)
    assert posted["reply_status"] == "posted" and "랩을 두 번" not in posted["reply_text"]  # 뺀 할 일의 조치는 약속하지 않는다
    assert sorted(hr_log()) == [("negative_reply", "approved"), ("review_fix_task", "rejected")]


def test_assistant_card_goes_to_the_window():
    donna, rid = staff_negative("assistant")
    assert repo.review(rid)["reply_status"] == "posted" and repo.all_of("notice", "s005") == []
    donna.clock("2026-11-17T16:10:00+09:00")
    asked = donna.open_notice()
    assert [i["job"] for i in asked["action"]["items"]] == ["review_fix_task"]
    assert asked["say"][-1]["text"] == "넣을까요?"
    donna.turn("응, 넣어")
    assert hr_log() == [("negative_reply", "done"), ("review_fix_task", "approved")]


def test_window_closes_at_closing_time():
    from voice.tests.conftest import choongjang

    donna = choongjang()
    donna.client.post("/v1/dev/hr", json={"store_id": "s005", "ranks": {"negative_reply": "staff"}})
    donna.clock("2026-11-17T20:10:00+09:00")  # 문 닫기(20:30) 20분 전
    donna.demo_review("leak")
    [batch] = repo.all_of("hr_batch", "s005")
    assert batch["due_at"] == "2026-11-17T20:30:00+09:00"


def test_unanswered_window_is_asked_next_morning():
    donna, rid = staff_negative()
    donna.clock("2026-11-17T16:10:00+09:00")
    donna.notices()  # 알림은 왔지만 열지 않았다
    donna.clock("2026-11-18T10:00:00+09:00")
    steps = briefing.current("s005")["steps"]
    assert {"job": "negative_reply", "ref": rid} in steps["negative"]["action"]["items"]
    assert "배달 용기 이중 실링" in steps["staff_tasks"]["say"][-1]["text"]


def test_intern_staff_tasks_are_asked_one_by_one():
    """리뷰 교정 할 일이 인턴이면 한 건씩 묻고, 정하면 다음 건을 바로 묻는다 (인사과 4-c)."""
    from voice import proposals
    from voice.context import load
    from voice.jobs import staff_tasks
    from voice.tests.conftest import choongjang

    choongjang(keep_tasks=True, at=None)
    assert len(proposals.for_briefing("s005", "2026-11-17")) == 2  # 픽스처의 면 교정 제안과 예약 메모의 알레르기 (규칙)
    proposals.create("s005", dept="customer", by="negative_review", ask_on="2026-11-17", dedupe=False,
                     payload={"title": "배달 용기 이중 실링", "detail": "랩을 두 번 씌워 주세요", "phase": "open", "days": 2,
                              "must_confirm": True, "urgent": False}, reason={"type": "review", "review_id": "rv_0410"})
    assert len(staff_tasks.step(load("s005"), clock.now())["tasks"]) == 3  # 사원: 묶어서
    hr.set_ranks("s005", {"review_fix_task": "intern"})
    first = staff_tasks.step(load("s005"), clock.now())
    assert len(first["tasks"]) == 1  # 인턴: 한 건씩
    session = {"tasks_pending": first["tasks"]}
    proposals.mark_asked(first["tasks"])
    following = staff_tasks.decide(load("s005"), "action.approve", None, session, "응, 넣어")
    assert following["type"] == "ask_tasks" and following["tasks"] != first["tasks"]  # 넣고 나서 다음 건을 바로 묻는다
    assert following["say"][0]["text"].startswith("알바생 할 일에 ")


def test_waiting_replies_go_out_once_promoted(monkeypatch):
    """사원일 때 써 두고 묻던 답글은 평가로 대리가 된 날 묻지 않는다. 아쉬운 리뷰 답글은 올리고 칭찬 답글은 예약한다 (known-bugs B3)."""
    import datetime as dt

    from voice import config
    from voice.clock import SEOUL
    from voice.tests.conftest import choongjang

    donna = choongjang()
    donna.client.post("/v1/dev/hr", json={"store_id": "s005", "ranks": {"negative_reply": "staff"}})
    with clock.at(dt.datetime(2026, 11, 10, 12, 0, tzinfo=SEOUL)):  # 지난 2주 그대로 승인 (시연 기록 5/9 에 더해 승진 기준을 넘게)
        for n in range(40):
            hr.record("s005", "negative_reply", f"past_{n}", "approved", "응")
    monkeypatch.setattr(config, "HR_EPOCH", dt.date(2026, 11, 18))  # 11/18 아침 준비가 평가일
    donna.clock("2026-11-17T22:40:00+09:00")  # 문 닫은 뒤: 바로 답하지 않고 아침에 묻는다
    rid = donna.demo_review("leak")
    donna.clock("2026-11-17T23:30:00+09:00")  # 바로 답하기(30분 안)는 사원이라 돌지 않고 지나갔다
    assert repo.review(rid)["reply_status"] == "none"
    awaiting = {r["id"] for r in repo.reviews("s005") if r.get("reply_status") == "awaiting"}
    assert awaiting
    donna.clock("2026-11-18T09:30:00+09:00")
    assert hr.rank("s005", "negative_reply") == "assistant" and hr.rank("s005", "positive_reply") == "assistant"
    posted = repo.review(rid)
    assert posted["reply_status"] == "posted" and posted["reply_text"] == posted["reply_ready"]["text"]
    steps = briefing.current("s005")["steps"]
    assert steps["negative"] is None and steps["scheduling"] is None  # 대리는 묻지 않는다
    assert ("negative_reply", "done") in hr_log()
    after = [repo.review(review_id) for review_id in awaiting]
    assert {r["reply_status"] for r in after} == {"scheduled"} and {r["reply_trigger"] for r in after} == {"auto"}
    assert all(clock.parse(r["reply_post_at"]) > clock.now() for r in after)  # 지난 때로 올리지 않는다
    donna.clock("2026-11-19T09:30:00+09:00")
    steps = briefing.current("s005")["steps"]
    # 다음 날 알린다: 바로 단 사과 답글은 H-10 단계가 보여 주고 보고하며 (report), 사후 보고(done_report)에서는 뺀다
    negative_reply = [e["id"] for e in hr.events("s005") if e["job"] == "negative_reply" and e["reaction"] == "done"]
    assert steps["negative_done"] is not None and steps["negative_done"]["report"] == negative_reply
    report = steps["done_report"]
    assert report is None or all(row["id"] != "dr_negative_reply" for row in report["cards"][0]["rows"])


def briefing_step(donna, key: str) -> dict:
    """아침 브리핑을 듣다가 그 단계에서 멈춘다."""
    response = donna.turn("오늘 일정 브리핑해 줘")
    while (response.get("briefing") or {}).get("step_key") != key:
        assert response["type"] != "end", f"{key} 단계가 없어요"
        response = donna.turn("다음")
    return response


def test_overnight_reply_does_not_promise_an_expired_fix():
    """밤사이 아쉬운 리뷰: 교정 할 일이 버려진(expired) 뒤 답글을 올리면 조치를 약속하지 않는 글로 (known-bugs B7)."""
    from voice import proposals
    from voice.tests.conftest import choongjang

    donna = choongjang()
    donna.client.post("/v1/dev/hr", json={"store_id": "s005", "ranks": {"negative_reply": "staff"}})
    donna.clock("2026-11-17T22:40:00+09:00")
    rid = donna.demo_review("leak")
    donna.clock("2026-11-18T09:30:00+09:00")
    ready = repo.review(rid)["reply_ready"]
    assert "랩을 두 번" in ready["text"] and ready["plain"] and "랩을 두 번" not in ready["plain"]
    donna.clock("2026-11-19T09:30:00+09:00")  # 11/18 브리핑을 듣지 않았다
    assert proposals.for_review("s005", rid)["state"] == "expired"
    assert {"job": "negative_reply", "ref": rid} in briefing_step(donna, "negative")["action"]["items"]
    donna.turn("응")
    assert repo.review(rid)["reply_status"] == "posted" and repo.review(rid)["reply_text"] == ready["plain"]


def test_failed_auto_reply_is_asked_next_morning(monkeypatch):
    """대리: 바로 답하기가 끝내 실패한 아쉬운 리뷰는 다음 아침 브리핑에서 묻는다 (known-bugs B6)."""
    from voice.jobs import auto_reply
    from voice.tests.conftest import choongjang

    donna = choongjang()
    donna.client.post("/v1/dev/hr", json={"store_id": "s005", "ranks": {"negative_reply": "assistant"}})
    summaries = auto_reply.REPLY_SUMMARIES
    monkeypatch.setattr(auto_reply, "REPLY_SUMMARIES", {})  # 바로 답하기에서만 오류
    donna.clock("2026-11-17T22:40:00+09:00")
    rid = donna.demo_review("leak")
    donna.clock("2026-11-17T23:30:00+09:00")
    monkeypatch.setattr(auto_reply, "REPLY_SUMMARIES", summaries)
    assert repo.review(rid)["reply_status"] == "none" and repo.review(rid)["auto_reply_failed_at"]
    donna.clock("2026-11-18T09:30:00+09:00")
    asked = briefing_step(donna, "negative")
    assert asked["action"]["items"] == [{"job": "negative_reply", "ref": rid}]  # 대리라 다른 리뷰는 묻지 않는다
    donna.turn("응")
    assert repo.review(rid)["reply_status"] == "posted" and ("negative_reply", "approved") in hr_log()


# ── 묶어 묻기 결재는 지금 리뷰를 다시 보고 쓴다 (2026-11-22 버그 V9) ──


def _posted_right_after_load(monkeypatch, rid: str) -> None:
    """말 처리를 시작해 가게 문서를 읽은 직후, 작업 큐가 같은 리뷰에 답글을 올린 것처럼 한다."""
    from voice.dialog import turn

    real = turn.load

    def load_then_posted(store_id):
        view = real(store_id)
        repo.save_review({**repo.review(rid), "reply_status": "posted", "reply_text": "먼저 올린 답글"})
        return view

    monkeypatch.setattr(turn, "load", load_then_posted)


def test_batch_reject_does_not_overwrite_a_reply_posted_meanwhile(monkeypatch):
    donna, rid = staff_negative()
    donna.clock("2026-11-17T16:10:00+09:00")
    donna.open_notice()
    _posted_right_after_load(monkeypatch, rid)
    donna.turn("안 해")
    found = repo.review(rid)
    assert found["reply_status"] == "posted" and found["reply_text"] == "먼저 올린 답글"
    assert ("negative_reply", "rejected") not in hr_log()


def test_batch_approve_does_not_overwrite_a_reply_posted_meanwhile(monkeypatch):
    donna, rid = staff_negative()
    donna.clock("2026-11-17T16:10:00+09:00")
    donna.open_notice()
    _posted_right_after_load(monkeypatch, rid)
    donna.turn("응")
    found = repo.review(rid)
    assert found["reply_status"] == "posted" and found["reply_text"] == "먼저 올린 답글"
    assert ("negative_reply", "approved") not in hr_log()


# ── 묶음 승인은 그 사이 접힌 할 일 제안을 넣지 않는다 (2026-11-22 버그 V11) ──


def test_batch_task_approve_skips_proposal_declined_meanwhile():
    from voice import proposals, staff
    from voice.context import load
    from voice.jobs import batch_ask
    from voice.tests.conftest import choongjang

    choongjang(keep_tasks=True, at=None)
    found = proposals.create("s005", dept="customer", by="negative_review", ask_on="2026-11-17", dedupe=False,
                             payload={"title": "배달 용기 이중 실링", "detail": "랩을 두 번 씌워 주세요", "phase": "open", "days": 2,
                                      "must_confirm": True, "urgent": False}, reason={"type": "review", "review_id": "rv_0410"})
    before = len(staff.store_tasks("s005"))
    proposals.decline(found["id"], "timeout")  # 사장님 "응" 처리 중에 작업 큐가 시간 넘김으로 접었다
    assert batch_ask._task_approve(load("s005"), found["id"]) is False
    assert proposals.get(found["id"])["state"] == "declined"
    assert len(staff.store_tasks("s005")) == before
