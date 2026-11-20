"""직급대로 동작 (인사과 9장 4단계, donna-voice/docs/agent-structure.md 4-1·9-0).

4-a 부정 리뷰 답글은 test_loop_negative(A 묶음), test_scenario_a·b, test_v021_choongjang 에서 본다.
"""

from voice import clock, hr, repo
from voice.instagram import posts
from voice.jobs import briefing
from voice.tests.conftest import FakeGraph, baseline, hr_log, prepared
from voice.tests.test_instagram import Choongjang, chj, connect, run_publish  # noqa: F401 (chj 는 fixture)


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
    connect(chj)
    chj.client.post("/v1/dev/hr", json={"store_id": "s005", "ranks": {"instagram_post": "staff"}})
    briefing.prepare("s005")
    assert briefing.current("s005")["steps"]["instagram"]["headline"] == "인스타에 올릴까요?"  # 하루 한 건이라 묶지 않는다 (9-0 e)
    assert hr.asks("s005", "instagram_post") == "batch" and clock.now().date().isoformat() == "2026-11-17"
