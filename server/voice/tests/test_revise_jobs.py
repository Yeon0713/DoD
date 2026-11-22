"""뒤에서 고치고 알리기 (감사팀 9장, jobs/revise_jobs.py): 대답은 고쳐 쓰기를 기다리지 않고, 고치는 동안 생기는 일(9-3)을 처리한다."""

import pytest

from voice import repo
from voice.agents import voice_reply
from voice.jobs import briefing, revise_jobs
from voice.tests.test_hr_revise import leak_alert


@pytest.fixture
def held(monkeypatch):
    """뒤에서 돌릴 작업을 붙잡아 두었다가 시험이 원할 때 돌린다 (앱 요청이 끝난 뒤 고쳐 쓰기가 끝나는 것처럼)."""
    waiting = []
    monkeypatch.setattr(revise_jobs, "spawn", lambda target, *args: waiting.append((target, args)))

    def run_all():
        while waiting:
            target, args = waiting.pop(0)
            target(*args)

    return run_all


@pytest.fixture
def rewriter(monkeypatch):
    calls = []

    def fake(view, review, kind, previous, instruction, occasion=None, fix=None):
        calls.append(instruction)
        return {"text": previous + " 고침", "source": "AGENT", "notes": [], "audit": {"passed": True, "rounds": 0}}

    monkeypatch.setattr(voice_reply, "revise", fake)
    return calls


def revise_notices(donna) -> list[dict]:
    return [n for n in donna.notices() if n["kind"] == "revise_ready"]


def test_answer_does_not_wait_for_the_rewrite(held, rewriter):
    donna, rid = leak_alert()
    told = donna.turn("좀 더 부드럽게 써 줘")
    assert told["say"][0]["text"] == "네, 고쳐서 알려 드릴게요." and rewriter == []  # 아직 고쳐 쓰지 않았다
    [job] = repo.all_of("revise_job", "s005")
    assert job["state"] == "running" and job["target"] == "alert"
    held()
    assert rewriter == ["좀 더 부드럽게 써 줘"] and revise_jobs.get(job["id"])["state"] == "ready"
    [notice] = revise_notices(donna)
    asked = donna.turn(event="notice", notice_id=notice["id"])
    assert asked["say"][0]["text"] == "이렇게 고쳤어요." and " 고침" in asked["cards"][0]["reply"]["text"]


def test_yes_while_rewriting_posts_the_current_text(held, rewriter):
    donna, rid = leak_alert()
    before = repo.get("alert", f"al_{rid}")["reply_base"]
    donna.turn("좀 더 부드럽게 써 줘")
    donna.turn("응, 진행해")
    assert repo.review(rid)["reply_status"] == "posted" and repo.review(rid)["reply_text"].startswith(before)
    held()  # 늦게 끝난 결과는 버린다
    assert repo.get("alert", f"al_{rid}")["reply_base"] == before and revise_notices(donna) == []
    assert repo.all_of("revise_job", "s005")[0]["state"] == "canceled"


def test_second_rewrite_cancels_the_first_and_joins_instructions(held, rewriter):
    donna, rid = leak_alert()
    donna.turn("좀 더 부드럽게 써 줘")
    donna.turn("더 짧게")
    first, second = repo.all_of("revise_job", "s005")
    assert first["state"] == "canceled" and second["instruction"] == "좀 더 부드럽게 써 줘, 더 짧게"
    held()
    assert rewriter == ["좀 더 부드럽게 써 줘, 더 짧게"]  # 취소한 작업은 고쳐 쓰지 않았거나 버렸다
    assert len(revise_notices(donna)) == 1


def test_day_change_expires_running_jobs(held, rewriter):
    donna, rid = leak_alert()
    donna.turn("좀 더 부드럽게 써 줘")
    donna.clock("2026-11-18T09:00:00+09:00")
    briefing.prepare("s005")
    [job] = repo.all_of("revise_job", "s005")
    assert job["state"] == "expired"
    held()
    assert revise_notices(donna) == []


def test_batch_yes_while_rewriting_keeps_the_current_text(held, rewriter):
    from voice.tests.test_hr_flow import staff_negative

    donna, rid = staff_negative()  # 부정 리뷰 답글 사원: 묶음 창
    donna.clock("2026-11-17T16:10:00+09:00")
    donna.open_notice()
    before = repo.review(rid)["reply_ready"]["text"]
    told = donna.turn("좀 더 부드럽게 써 줘")
    assert told["say"][0]["text"] == "네, 고쳐서 알려 드릴게요."
    donna.turn("응")
    assert repo.review(rid)["reply_status"] == "posted" and repo.review(rid)["reply_text"] == before
    held()
    assert repo.review(rid)["reply_text"] == before and revise_notices(donna) == []


def test_batch_rewrite_then_notice_asks_again(held, rewriter):
    from voice.tests.test_hr_flow import staff_negative

    donna, rid = staff_negative()
    donna.clock("2026-11-17T16:10:00+09:00")
    donna.open_notice()
    donna.turn("좀 더 부드럽게 써 줘")
    held()
    [notice] = revise_notices(donna)
    asked = donna.turn(event="notice", notice_id=notice["id"])
    assert asked["type"] == "ask_action" and asked["say"][0]["text"] == "이렇게 고쳤어요."
    donna.turn("응")
    assert " 고침" in repo.review(rid)["reply_text"]


def test_failed_job_notice_says_so(held, monkeypatch):
    monkeypatch.setattr(voice_reply, "revise", lambda *a, **k: None)
    donna, rid = leak_alert()
    donna.turn("좀 더 부드럽게 써 줘")
    held()
    [notice] = revise_notices(donna)
    assert notice["text"] == "글을 고치지 못했어요"
    asked = donna.turn(event="notice", notice_id=notice["id"])
    assert [s["text"] for s in asked["say"][:2]] == ["지금은 고치지 못했어요.", "이대로 올릴지 다시 말씀해 주세요."]
