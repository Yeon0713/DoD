"""감사팀 settle: 업무 · 직급 · 감사 결과마다 끝내 불합격 처리 (감사팀 계획 8-3, 결정 7, 가정 g)."""

import pytest

from voice import audit, hr

PASS, FAIL, UNCHECKED = {"passed": True}, {"passed": False}, {"passed": None}


@pytest.mark.parametrize("rank", hr.RANKS)
@pytest.mark.parametrize("job", ["negative_reply", "positive_reply", "instagram_post", "review_fix_task", "field_task"])
def test_pass_and_no_audit_are_ok(job, rank):
    hr._start("s1", job, rank)
    assert audit.settle("s1", job, PASS) == "ok"
    assert audit.settle("s1", job, None) == "ok"


@pytest.mark.parametrize("job", sorted(audit.STAFF_TASK_JOBS))
@pytest.mark.parametrize("found", [FAIL, UNCHECKED])
def test_staff_tasks_fall_back(job, found):
    hr._start("s1", job, "staff")
    assert audit.settle("s1", job, found) == "fallback"


@pytest.mark.parametrize("found", [FAIL, UNCHECKED])
def test_fact_checks_fall_back(found):
    assert audit.settle("s1", "holiday", found) == "fallback"


@pytest.mark.parametrize("rank, fail, unchecked", [
    ("intern", "template", "ok"), ("staff", "template", "ok"), ("assistant", "hold", "hold"), ("manager", "hold", "hold")])
def test_reply_by_rank(rank, fail, unchecked):
    hr._start("s1", "positive_reply", rank)
    assert audit.settle("s1", "positive_reply", FAIL) == fail
    assert audit.settle("s1", "positive_reply", UNCHECKED) == unchecked


def test_cap_applies_before_deciding():
    hr._start("s1", "negative_reply", "manager")  # 부정 답글 상한은 대리 → 대리로 본다 (묻지 않음)
    assert audit.settle("s1", "negative_reply", FAIL) == "hold"
    hr._start("s1", "instagram_post", "assistant")
    assert audit.settle("s1", "instagram_post", FAIL, offer=True) == "template"  # 혜택 포스터는 늘 결재 (상한 사원)


def test_version_changes_with_prompts(tmp_path, monkeypatch):
    before = audit.version()
    folder = tmp_path / "prompts"
    folder.mkdir()
    (folder / "x.txt").write_text("새 기준", encoding="utf-8")
    monkeypatch.setattr(audit, "HERE", tmp_path)
    assert audit.version() != before
