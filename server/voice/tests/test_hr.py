"""인사과 바탕 (voice/hr.py, donna-voice/docs/agent-structure.md 4장·9장 2단계)."""

import datetime as dt

from voice import clock, config, hr, repo
from voice.clock import SEOUL
from voice.jobs import briefing
from voice.tests.conftest import choongjang

REVIEW_DAY = dt.date(2026, 11, 30)  # 첫 평가일 (월)
IN_PERIOD = dt.datetime(2026, 11, 20, 15, 0, tzinfo=SEOUL)


def put_rank(store_id: str, job: str, rank: str) -> None:
    hr._start(store_id, job, rank)


def react(store_id: str, job: str, reactions: list[str], at: dt.datetime = IN_PERIOD) -> None:
    with clock.at(at):
        for i, reaction in enumerate(reactions):
            hr.record(store_id, job, f"ref_{job}_{reaction}_{i}", reaction, "응")


def test_nine_of_ten_promotes_and_eight_stays():
    react("s1", "review_fix_task", ["approved"] * 9 + ["rejected"])
    react("s2", "review_fix_task", ["approved"] * 8 + ["edited"] * 2)
    hr.evaluate("s1", REVIEW_DAY)
    hr.evaluate("s2", REVIEW_DAY)
    assert hr.rank("s1", "review_fix_task") == "staff" and hr.rank("s2", "review_fix_task") == "intern"
    assert hr.stored("s1", "review_fix_task")["changed_by"] == "promote"


def test_too_few_stays():
    react("s1", "review_fix_task", ["approved"] * 4)
    review = hr.evaluate("s1", REVIEW_DAY)
    assert hr.rank("s1", "review_fix_task") == "intern"
    [row] = [r for r in review["per_job"] if r["job"] == "review_fix_task"]
    assert row == {"job": "review_fix_task", "count": 4, "approved": 4, "canceled": 0, "before": "intern", "after": "intern"}


def test_records_outside_two_weeks_do_not_count():
    react("s1", "review_fix_task", ["approved"] * 3, at=dt.datetime(2026, 11, 15, 12, 0, tzinfo=SEOUL))  # 평가일 15일 전
    react("s1", "review_fix_task", ["approved"] * 3)
    hr.evaluate("s1", REVIEW_DAY)
    assert hr.rank("s1", "review_fix_task") == "intern"


def test_one_step_at_a_time_and_never_above_the_cap():
    react("s1", "positive_reply", ["approved"] * 20)
    put_rank("s1", "field_task", "staff")
    react("s1", "field_task", ["approved"] * 10)
    hr.evaluate("s1", REVIEW_DAY)
    assert hr.rank("s1", "positive_reply") == "staff"  # 인턴 → 사원 (대리로 건너뛰지 않음)
    assert hr.rank("s1", "field_task") == "staff"  # 알바생 할 일의 상한은 사원


def test_assistant_to_manager_needs_done_and_no_cancel():
    put_rank("s1", "positive_reply", "assistant")
    react("s1", "positive_reply", ["done"] * 20)
    put_rank("s2", "positive_reply", "assistant")
    react("s2", "positive_reply", ["done"] * 20 + ["canceled_after"])
    hr.evaluate("s1", REVIEW_DAY)
    hr.evaluate("s2", REVIEW_DAY)
    assert hr.rank("s1", "positive_reply") == "manager" and hr.rank("s2", "positive_reply") == "assistant"
    put_rank("s3", "negative_reply", "assistant")
    react("s3", "negative_reply", ["done"] * 20)
    hr.evaluate("s3", REVIEW_DAY)
    assert hr.rank("s3", "negative_reply") == "assistant"  # 부정 답글의 상한은 대리


def test_cancel_after_demotes_at_once():
    put_rank("s1", "negative_reply", "assistant")
    assert hr.demote("s1", "negative_reply", "rv_1") == "staff" and hr.asks("s1", "negative_reply") == "batch"
    put_rank("s1", "positive_reply", "manager")
    assert hr.demote("s1", "positive_reply", "rv_2") == "assistant"
    assert hr.demote("s1", "review_fix_task", "pr_1") is None  # 인턴·사원은 강등이 없다
    put_rank("s1", "story_poster", "staff")
    assert hr.demote("s1", "story_poster", "se_1", offer=True) == "intern"  # 혜택 포스터의 사고는 인턴으로
    assert [h["by"] for h in hr.stored("s1", "negative_reply")["history"]] == ["start", "demote"]


def test_same_review_day_runs_once():
    react("s1", "review_fix_task", ["approved"] * 4)
    assert hr.evaluate("s1", REVIEW_DAY) is not None
    react("s1", "review_fix_task", ["approved"] * 6)
    assert hr.evaluate("s1", REVIEW_DAY + dt.timedelta(days=1)) is None  # 같은 평가일(11/30)의 평가는 이미 했다
    assert hr.rank("s1", "review_fix_task") == "intern"
    assert hr.evaluate("s1", dt.date(2026, 11, 29)) is None  # 첫 평가일 전


def test_offer_poster_is_capped_at_staff():
    put_rank("s1", "story_poster", "assistant")
    assert hr.asks("s1", "story_poster") is None
    assert hr.rank("s1", "story_poster", offer=True) == "staff" and hr.asks("s1", "story_poster", offer=True) == "batch"


def test_new_store_starts_as_intern():
    assert hr.asks("s9", "negative_reply") == "each" and hr.stored("s9", "negative_reply")["changed_by"] == "start"


def test_migrate_matches_the_start_table():
    for sid, auto in (("s1", True), ("s2", None)):
        repo.put("store", sid, sid, {"id": sid})
        repo.save_settings(sid, {"negative_review_auto_reply": auto})
    put_rank("s2", "instagram_post", "assistant")  # 이미 있는 직급은 두지 않는다
    done = hr.migrate()
    assert done["s1"] == {"positive_reply": "manager", "negative_reply": "assistant", "instagram_post": "intern",
                          "story_poster": "intern", "review_fix_task": "staff", "field_task": "staff", "manual_task": "staff"}
    assert done["s2"]["negative_reply"] == "intern" and "instagram_post" not in done["s2"]
    assert hr.rank("s2", "instagram_post") == "assistant" and hr.migrate() == {}


def test_heavier_reaction_wins_for_one_decision():
    hr.record("s1", "negative_reply", "al_1", "edited", "좀 더 부드럽게")
    hr.record("s1", "negative_reply", "al_1", "approved", "응")
    hr.record("s1", "negative_reply", "al_2", "approved", "응")
    hr.record("s1", "negative_reply", "al_2", "rejected", "안 해")
    assert [(e["ref"], e["reaction"]) for e in hr.events("s1")] == [("al_1", "edited"), ("al_2", "rejected")]


def test_switch_off_records_and_evaluates_nothing(monkeypatch):
    monkeypatch.setenv("VOICE_HR", "false")
    assert hr.record("s1", "negative_reply", "al_1", "approved") is None and hr.events("s1") == []
    put_rank("s1", "negative_reply", "assistant")
    assert hr.evaluate("s1", REVIEW_DAY) is None and hr.demote("s1", "negative_reply", "rv_1") is None
    assert hr.rank("s1", "negative_reply") == "assistant"  # 직급은 저장된 그대로 읽는다


def test_briefing_prepare_runs_the_review():
    choongjang(at=None)
    clock.set_now(dt.datetime(2026, 11, 30, 9, 0, tzinfo=SEOUL))
    briefing.prepare("s005")
    assert repo.get(hr.REVIEW_KIND, "s005:2026-11-30")["period"] == ["2026-11-16", "2026-11-30"]
    assert config.HR_EPOCH.weekday() == 0  # 월요일


def test_fixture_history_backs_the_demo_ranks():
    """s005 시나리오 파일의 지난 2주 기록 (9-2의 1). 직급은 파일의 hr 칸이 정하고, 기록은 그 근거다."""
    choongjang(at=None)
    history = [e for e in hr.events("s005") if e["ref"].startswith("hist_")]
    by_job = {job: [e["reaction"] for e in history if e["job"] == job] for job in hr.JOBS}
    assert len(by_job["positive_reply"]) == 22 and by_job["positive_reply"].count("approved") / 22 >= config.HR_PROMOTE_RATIO
    assert by_job["negative_reply"].count("approved") / len(by_job["negative_reply"]) < config.HR_PROMOTE_RATIO
    assert min(e["at"] for e in history) == "2026-11-03T12:00:00+09:00" and max(e["at"] for e in history) <= "2026-11-16T12:00:00+09:00"
