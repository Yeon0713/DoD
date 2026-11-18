"""질문 1~5 카드 계산(Harness/evals/scorecard.py): 사례 단위 다수결, 표본 부족, 안 돌림, 구간, 목표 통과, 실행 고르기."""

import pytest

from Harness.evals import metrics, scorecard
from Harness.evals.scorecard import ITEM_BY_KEY, majority


def body(suite, folder, systems, rows=(), cases=(), *, started="2026-11-18T10:00:00+09:00", config=None, commit="abc1234"):
    return {"schema": 1, "suite": suite, "_folder": f"/x/{folder}", "started_at": started, "systems": list(systems),
            "git": {"commit": commit, "dirty": False}, "config": config or {}, "metrics": list(rows), "cases": list(cases)}


def metric(id, system, numerator, denominator, **keys):
    return {**metrics.metric(id, id, question=4, system=system, numerator=numerator, denominator=denominator), **keys}


def item_of(card, key):
    return next(item for q in card["questions"] for item in q["items"] if item["key"] == key)


def cell_of(card, key, system):
    return next(cell for cell in item_of(card, key)["cells"] if cell["system"] == system)


def kitchen(case_id, run, intent, system="rule+judge"):
    return {"case_id": case_id, "system": system, "run": run, "expected_intent": "not_for_donna", "intent": intent,
            "addressed": False, "source": "kitchen", "context": {"briefing_step": 1, "last_type": "answer"}}


# ── 순수 함수 ──


def test_majority_ties_go_to_the_bad_side():
    assert majority([True, True, False], lower_better=True) is True
    assert majority([True, False, False], lower_better=False) is False
    assert majority([True, False], lower_better=True) is True  # 놓침률 반반 → 놓침
    assert majority([True, False], lower_better=False) is False  # 정확도 반반 → 틀림


def test_case_level_counts_each_case_once():
    item = ITEM_BY_KEY["q4.false_activation"]
    rows = [kitchen("k1", r, "briefing.next") for r in (1, 2, 3)]  # 세 번 다 반응
    rows += [kitchen("k2", 1, "briefing.next"), kitchen("k2", 2, "not_for_donna"), kitchen("k2", 3, "not_for_donna")]
    rows += [{**kitchen("x", 1, "stop"), "expected_intent": "stop"}]  # 분모 밖
    counted = scorecard.case_level(rows, scorecard.rule_for(item), item)
    assert counted == {"numerator": 1, "denominator": 2, "run_numerator": 4, "run_denominator": 6}


def test_status_threshold():
    assert scorecard.status_of(9) == "too_few" and scorecard.status_of(10) == "ok" and scorecard.status_of(None) == "too_few"


# ── 카드 ──


def test_not_run_when_no_result_and_for_missing_systems():
    card = scorecard.scorecard([body("intent", "intent-1", ["rule"], [metric("false_activation_rate", "rule", 0, 39)])])
    assert cell_of(card, "q4.false_activation", "rule")["status"] == "ok"
    missing = cell_of(card, "q4.false_activation", "rule+judge")
    assert missing["status"] == "not_run" and missing["passed"] is None and missing["folder"] is None
    assert all(cell["status"] == "not_run" for cell in item_of(card, "q5.turn_briefing")["cells"])
    assert [q["title"] for q in card["questions"]] == list(scorecard.QUESTIONS.values())


def test_single_run_uses_metric_row_with_wilson_interval_and_target():
    rows = [metric("missed_command_rate_addressed", "rule", 0, 19), metric("false_activation_rate", "rule", 3, 39)]
    card = scorecard.scorecard([body("intent", "intent-1", ["rule"], rows)])
    addressed = cell_of(card, "q4.missed_addressed", "rule")
    assert (addressed["numerator"], addressed["denominator"], addressed["status"], addressed["passed"]) == (0, 19, "ok", True)
    low, high = addressed["interval"]
    assert low == 0.0 and high == pytest.approx(metrics.wilson_interval(0, 19)[1])
    false_activation = cell_of(card, "q4.false_activation", "rule")
    assert false_activation["passed"] is None  # 숫자 목표가 없다
    assert addressed["folder"] == "intent-1" and addressed["commit"] == "abc1234"


def test_too_few_has_no_pass_badge():
    card = scorecard.scorecard([body("intent", "intent-1", ["rule"], [metric("missed_command_rate_addressed", "rule", 1, 5)])])
    cell = cell_of(card, "q4.missed_addressed", "rule")
    assert cell["status"] == "too_few" and cell["passed"] is None and cell["value"] == 0.2


def test_multiple_runs_switch_to_case_level_majority():
    cases = [kitchen(f"k{n}", r, "briefing.next" if (n == 0 or (n == 1 and r == 1)) else "not_for_donna")
             for n in range(12) for r in (1, 2, 3)]
    rows = [metric("false_activation_rate", "rule+judge", 4, 36)]  # 회차 합 (사례 단위가 아님)
    card = scorecard.scorecard([body("intent", "intent-1", ["rule+judge"], rows, cases)])
    cell = cell_of(card, "q4.false_activation", "rule+judge")
    assert (cell["numerator"], cell["denominator"]) == (1, 12)  # k0 만 과반 반응
    assert cell["run_fraction"] == "4/36" and cell["runs"] == 3 and "다수결" in cell["note"]
    assert cell["interval"] == pytest.approx(list(metrics.wilson_interval(1, 12)))


def test_multiple_runs_without_rule_drop_interval():
    rows = [metric("negative_recall", "hcx", 30, 48, set="balanced")]
    cases = [{"case_id": "c1", "system": "hcx", "run": 3}]
    cell = cell_of(scorecard.scorecard([body("label", "label-1", ["hcx"], rows, cases)]), "q1.negative_recall", "hcx")
    assert cell["interval"] is None and cell["case_level"] is False and cell["run_fraction"] == "30/48"


def test_old_guards_result_is_recomputed_from_cases():
    good = [{"case_id": f"n{i}", "system": "critic", "run": 1, "set": "normal", "expected_ok": True, "kinds": [],
             "outcome": "false_reject" if i < 2 else "pass", "detected": ["compensation"] if i < 2 else []} for i in range(12)]
    card = scorecard.scorecard([body("guards", "guards-1", ["critic"], [], good)])
    cell = cell_of(card, "q3.compensation_false_alarm", "critic")
    assert (cell["numerator"], cell["denominator"], cell["recomputed"], cell["passed"]) == (2, 12, True, False)


def test_latency_percentiles_and_target():
    cases = [{"case_id": f"turn:{i}", "system": "rule+judge", "run": 1, "kind": "briefing", "seconds": 0.1 * i, "error": None}
             for i in range(1, 13)]
    cases.append({"case_id": "turn:99", "system": "rule+judge", "run": 1, "kind": "briefing", "seconds": None, "error": "HTTP 500"})
    card = scorecard.scorecard([body("voice", "voice-1", ["rule+judge"], [], cases)])
    cell = cell_of(card, "q5.turn_briefing", "rule+judge")
    assert cell["n"] == 12 and cell["errors"] == 1 and cell["p50"] == pytest.approx(0.6) and cell["p95"] == pytest.approx(1.2)
    assert cell["status"] == "ok" and cell["passed"] is False  # p95 1.2초 > 1초
    assert cell_of(card, "q5.turn_question", "rule+judge")["status"] == "not_run"


def test_latest_run_by_default_pick_and_baseline_diff():
    old = body("intent", "intent-old", ["rule"], [metric("false_activation_rate", "rule", 6, 40)], started="2026-11-17T09:00:00+09:00",
               config={"baseline": True}, commit="old0001")
    new = body("intent", "intent-new", ["rule"], [metric("false_activation_rate", "rule", 2, 40)], started="2026-11-18T09:00:00+09:00")
    card = scorecard.scorecard([old, new])
    cell = cell_of(card, "q4.false_activation", "rule")
    assert cell["folder"] == "intent-new" and cell["baseline_diff"] == pytest.approx(-0.1) and cell["baseline_folder"] == "intent-old"
    assert [o["folder"] for o in item_of(card, "q4.false_activation")["options"]] == ["intent-new", "intent-old"]
    picked = scorecard.scorecard([old, new], {"q4.false_activation": "intent-old"})
    assert cell_of(picked, "q4.false_activation", "rule")["folder"] == "intent-old"
    assert cell_of(picked, "q4.false_activation", "rule")["baseline_diff"] is None  # 기준점 자신
    assert item_of(picked, "q4.false_activation")["picked"] == "intent-old"


def test_reply_items_pick_runs_by_split():
    tune = body("reply", "reply-tune", ["A"], [metric("reply_fit_rate", "A", 30, 48)], config={"split": "tune"},
                started="2026-11-17T09:00:00+09:00")
    injection = body("reply", "reply-inj", ["A"], [metric("reply_fit_rate", "A", 1, 20), metric("injection_follow_rate", "A", 2, 20)],
                     config={"split": "injection"}, started="2026-11-18T09:00:00+09:00")
    card = scorecard.scorecard([tune, injection])
    assert cell_of(card, "q2.reply_fit_rate", "A")["folder"] == "reply-tune"
    assert cell_of(card, "q4.injection_follow", "A")["folder"] == "reply-inj"


def test_noise_items_follow_level_and_f1_has_no_interval():
    rows = [metric("intent_accuracy", "rule", 200, 243, noise=0), metric("intent_accuracy", "rule", 80, 243, noise=3)]
    card = scorecard.scorecard([body("noise", "noise-1", ["rule"], rows),
                                body("label", "label-1", ["hcx"], [{**metrics.value_metric("sentiment_macro_f1", "", question=1,
                                     system="hcx", value=0.62, unit="f1"), "set": "balanced"}])])
    assert cell_of(card, "q1.noise3", "rule")["numerator"] == 80 and cell_of(card, "q1.noise1", "rule")["status"] == "not_run"
    f1 = cell_of(card, "q1.sentiment_macro_f1", "hcx")
    assert f1["value"] == 0.62 and f1["interval"] is None and f1["status"] == "ok"


def test_legacy_results_are_ignored():
    legacy = {"_folder": "/x/critic-1", "suite": "guards", "summary": {}, "rows": []}
    card = scorecard.scorecard([legacy])
    assert all(cell["status"] == "not_run" for cell in item_of(card, "q3.missed_compensation")["cells"])
