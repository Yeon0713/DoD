"""작업 큐의 신뢰성.

- 아쉬운 리뷰 알림(review_alert·remind·fallback)은 브리핑 준비(LLM)가 도는 동안에도 돈다 (알림 줄과 나머지 줄).
- 작업이 예외로 끝나면 끝난 것으로 적지 않고 조금 뒤 다시 한다. 정한 횟수를 넘기면 실패로 남기고 활동 기록에 적는다.
- 브리핑 준비가 예전에 읽은 리뷰로 알림이 바꾼 상태를 덮지 않는다.
"""

import datetime as dt
import threading

from voice import clock, context, repo
from voice.jobs import auto_reply, briefing, label, queue, review_loop
from voice.tests.conftest import choongjang


def negative_review(review_id: str = "rv_9001") -> dict:
    """시연 리뷰 leak(국물 샘)을 지금 시각에 넣는다. 작업은 돌리지 않는다."""
    item = repo.get("demo_review", "s005:leak")
    fields = {k: item[k] for k in ("platform", "rating", "text", "order_channel", "menus") if k in item}
    return repo.save_review(label.label({**fields, "store_id": "s005", "id": review_id, "reply_status": "none",
                                         "written_at": clock.iso(clock.now())}))


# ── 알림 줄 ──


def test_alert_runs_while_briefing_is_being_prepared(monkeypatch):
    choongjang()
    started, release = threading.Event(), threading.Event()
    real_prepare = briefing.prepare

    def slow_prepare(store_id):
        started.set()
        release.wait(5)
        return real_prepare(store_id)

    monkeypatch.setattr(briefing, "prepare", slow_prepare)
    queue.add("s005", "prepare_briefing", clock.now() - dt.timedelta(seconds=1))  # 픽스처가 이미 돌린 작업과 id 가 겹치지 않게
    slow = threading.Thread(target=queue.run_due, kwargs={"lane": "slow"})
    slow.start()
    try:
        assert started.wait(5)
        review = negative_review()
        review_loop.on_new_review(review)
        ran = queue.run_due(lane="alert")
        assert any(":review_alert:" in job_id for job_id in ran)
        assert repo.get("alert", f"al_{review['id']}")["state"] == "alerted"
    finally:
        release.set()
        slow.join(10)


def test_lanes_split_jobs_by_kind():
    choongjang()
    review = negative_review()
    review_loop.on_new_review(review)
    queue.add("s005", "post_scheduled", clock.now() - dt.timedelta(seconds=2))
    ran = queue.run_due(lane="alert")
    assert ran and all(":review_" in job_id for job_id in ran)
    assert all(":review_" not in job_id for job_id in queue.run_due(lane="slow"))


# ── 실패한 작업 ──


def test_failed_job_is_retried_then_marked_failed(monkeypatch):
    choongjang()
    start = clock.now()
    job = queue.add("s005", "post_scheduled", start - dt.timedelta(seconds=3))
    tried = []

    def broken(store_id):
        tried.append(clock.now())
        raise RuntimeError("플랫폼이 응답하지 않아요")

    monkeypatch.setattr(auto_reply, "post_scheduled", broken)
    queue.run_due()
    saved = repo.get("job", job["id"])
    assert saved["done"] is False and saved["attempts"] == 1 and "플랫폼이 응답하지 않아요" in saved["last_error"]
    assert clock.parse(saved["due_at"]) == start + queue.RETRY_DELAYS[0]

    for delay in queue.RETRY_DELAYS:
        clock.set_now(clock.parse(repo.get("job", job["id"])["due_at"]))
        queue.run_due()
    saved = repo.get("job", job["id"])
    assert len(tried) == len(queue.RETRY_DELAYS) + 1
    assert saved["done"] is True and saved["status"] == "failed" and saved["attempts"] == len(queue.RETRY_DELAYS) + 1
    logged = [a for a in repo.all_of("activity", "s005") if a["id"].endswith(f"job_failed:{job['id']}")]
    assert len(logged) == 1


def test_finished_job_is_marked_done():
    choongjang()
    job = queue.add("s005", "post_scheduled", clock.now() - dt.timedelta(seconds=4))
    queue.run_due()
    saved = repo.get("job", job["id"])
    assert saved["done"] is True and saved["status"] == "done" and saved.get("attempts", 1) == 1


# ── 브리핑 준비가 알림 상태를 덮지 않기 ──


def test_prepare_does_not_overwrite_alert_state_with_stale_review():
    choongjang()
    review = negative_review()
    stale = context.load("s005")  # 브리핑 준비가 먼저 읽은 모습 (reply_status none)
    review_loop.alert("s005", review["id"])  # 준비가 답글을 쓰는 사이 알림이 proposed 로 바꾼다
    briefing.draft_negative(stale)
    saved = repo.review(review["id"])
    assert saved["reply_status"] == "proposed" and saved["cause"] == "packaging"


def test_batch_window_notice_is_on_the_alert_lane():
    """사원 업무 묶음 창 알림(hr_batch, 인사과 4-c)도 30분 안에 가야 해서 브리핑 준비를 기다리지 않는다 (2026-11-21 머지 때 더함)."""
    assert queue.lane_of("hr_batch") == "alert" and queue.lane_of("prepare_briefing") == "slow"
