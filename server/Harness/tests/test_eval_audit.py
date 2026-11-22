"""감사 판정 평가(audit_eval)의 세트 읽기와 요약 숫자. CLOVA 를 부르지 않는다."""

from Harness.evals import audit_eval


def _row(run, case_id, expected, got, criterion="card_promise"):
    return {"run": run, "id": case_id, "job": "negative_reply", "criterion": criterion, "expected_ok": expected, "got_ok": got}


def test_critic_cases_are_reused_as_reply_job():
    cases = audit_eval.load_cases(job="reply")
    assert len(audit_eval.load_cases()) > len(cases)
    assert cases and all(c["criterion"] == "critic" for c in cases)


def test_summary_counts_miss_false_unknown_and_goal():
    rows = [_row(1, "a", False, True), _row(1, "b", False, False), _row(1, "c", True, False), _row(1, "d", True, None)]
    [found] = audit_eval.summarize(rows)
    assert (found["missed"], found["bad_total"], found["false_reject"], found["good_total"], found["unknown"]) == (1, 2, 1, 2, 1)
    assert found["meets_goal"] is False and found["unstable"] is None


def test_summary_counts_unstable_over_runs():
    rows = [_row(1, "a", False, False), _row(2, "a", False, True), _row(1, "b", True, True), _row(2, "b", True, True)]
    [found] = audit_eval.summarize(rows)
    assert found["unstable"] == 1
