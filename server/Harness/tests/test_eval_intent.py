"""intent 스위트(Harness/evals/intent_eval.py): 뜻 판정 정답 세트와 채점. 가짜 CLOVA 로만 본다."""

import json
import os

import httpx
import pytest

from app.core.config import settings
from Harness.evals import cli, intent_eval, report


class IntentClova:
    """submit_intent 요청에 들어온 말을 보고 정해 둔 뜻으로 답한다. 없는 말은 default."""

    def __init__(self, answers: dict[str, str], default: str = "not_for_donna", status: int = 200):
        self.answers = answers
        self.default = default
        self.status = status
        self.requests = []

    def __call__(self, url, headers=None, json=None, timeout=None):
        self.requests.append(json)
        if self.status != 200:
            return httpx.Response(self.status, json={"status": {"code": str(self.status)}}, request=httpx.Request("POST", url))
        user = next(m["content"] for m in json["messages"] if m["role"] == "user")
        text = user.split('"')[1]
        intent = self.answers.get(text, self.default)
        arguments = {"intent": intent, "owner_said": text}
        if intent == "briefing.jump":
            arguments["jump_to"] = "reviews"
        message = {"role": "assistant", "content": "", "toolCalls": [
            {"id": "call_1", "type": "function", "function": {"name": "submit_intent", "arguments": arguments}}]}
        payload = {"status": {"code": "20000"}, "result": {"message": message, "finishReason": "tool_calls",
                                                             "usage": {"promptTokens": 50, "completionTokens": 5}}}
        return httpx.Response(200, json=payload, request=httpx.Request("POST", url))


@pytest.fixture
def cases():
    return intent_eval.load_cases()[1]


# ── 정답 세트 ──


def test_dataset_shape_and_counts(cases):
    body, _ = intent_eval.load_cases()
    assert "verified_by" in body and len({c["id"] for c in cases}) == len(cases)
    by_source = {}
    for case in cases:
        by_source.setdefault(case["source"], []).append(case)
        assert set(case["context"]) == {"briefing_step", "donna_was_speaking", "last_type"}
    assert len(by_source["kitchen"]) == 20 and len(by_source["unknown"]) == 10 and len(by_source["scenario_c"]) == 8
    intents = {c["expected_intent"] for c in by_source["paraphrase"]}
    assert all(sum(c["expected_intent"] == i for c in by_source["paraphrase"]) == 5 for i in intents)
    assert all(sum(c["expected_intent"] == i for c in by_source["typo"]) == 3 for i in intents)
    from voice.agents.intent_judge import INTENTS
    assert {c["expected_intent"] for c in cases} <= set(INTENTS)


def test_scenario_c_matches_voice_tests(cases):
    """시나리오 C 는 voice/tests/test_scenario_c.py 와 같은 결과 (규칙 + heuristic, 에이전트 꺼짐)."""
    view = intent_eval.make_view()
    for case in (c for c in cases if c["source"] == "scenario_c"):
        got = intent_eval.classify("rule", case, view)
        assert intent_eval.is_correct(case, got), (case["id"], got)


# ── 채점 ──


def test_rule_system_never_calls_clova(cases, monkeypatch):
    monkeypatch.setattr(settings, "clova_studio_api_key", "test-key")
    post = IntentClova({})
    result = intent_eval.evaluate(cases, ["rule"], runs=3, post=post)
    assert post.requests == [] and len(result["cases"]) == len(cases)  # rule 은 회차와 무관하게 한 번
    ids = {m["id"]: m for m in result["metrics"]}
    assert set(ids) == {"intent_accuracy", "wrong_answer_rate", "missed_command_rate", "rule_coverage",
                        "false_activation_rate", "window_false_answer_rate", "missed_command_rate_addressed",
                        "wake_accept_rate", "wake_false_accept_rate"}
    assert ids["rule_coverage"]["denominator"] == len(cases)


def test_judge_answers_unmatched_and_counts_wrong_answers(monkeypatch):
    monkeypatch.setattr(settings, "clova_studio_api_key", "test-key")
    ctx = {"briefing_step": 1, "donna_was_speaking": False, "last_type": "answer"}
    data = [
        {"id": "a", "text": "다음", "addressed": False, "context": ctx, "expected_intent": "briefing.next"},  # 규칙
        {"id": "b", "text": "면 삶아", "addressed": False, "context": ctx, "expected_intent": "not_for_donna"},  # 판정: 맞음
        {"id": "c", "text": "도나 그거 있잖아", "addressed": False, "context": ctx, "expected_intent": "unknown"},  # 판정: 틀리게 답함
        {"id": "d", "text": "예약 몇 팀이야", "addressed": False, "context": ctx, "expected_intent": "question"},  # 판정: 무시
    ]
    post = IntentClova({"면 삶아": "not_for_donna", "도나 그거 있잖아": "briefing.start", "예약 몇 팀이야": "not_for_donna"})
    before = os.environ.get("VOICE_AGENT_INTENT")
    result = intent_eval.evaluate(data, ["rule+judge"], runs=2, post=post)
    assert os.environ.get("VOICE_AGENT_INTENT") == before
    assert len(post.requests) == 6 and result["calls"] == 6  # 규칙이 못 가른 3건 × 2회
    rows = {(r["case_id"], r["run"]): r for r in result["cases"]}
    assert rows[("a", 1)]["by"] == "rule" and rows[("b", 1)]["by"] == "llm" and rows[("b", 1)]["judge_seconds"] is not None
    m = {x["id"]: x for x in result["metrics"]}
    assert (m["intent_accuracy"]["numerator"], m["intent_accuracy"]["denominator"]) == (4, 8)
    assert (m["wrong_answer_rate"]["numerator"], m["wrong_answer_rate"]["denominator"]) == (2, 4)
    assert (m["missed_command_rate"]["numerator"], m["missed_command_rate"]["denominator"]) == (2, 4)
    assert m["rule_coverage"]["value"] == 0.25 and m["judge_within_budget"]["denominator"] == 6
    assert result["confusion"]["rule+judge"]["unknown → briefing.start"] == 2


def test_judge_failure_falls_back_to_heuristic(monkeypatch):
    monkeypatch.setattr(settings, "clova_studio_api_key", "test-key")
    case = {"id": "x", "text": "그거 뭐였지 그 저기", "addressed": False,
            "context": {"briefing_step": 1, "donna_was_speaking": False, "last_type": "answer"}, "expected_intent": "unknown"}
    (row,) = intent_eval.evaluate([case], ["rule+judge"], post=IntentClova({}, status=500))["cases"]
    assert row["by"] == "heuristic" and row["intent"] == "unknown" and row["correct"]


def test_addressed_speech_ignores_judge_not_for_donna(monkeypatch):
    monkeypatch.setattr(settings, "clova_studio_api_key", "test-key")
    case = {"id": "y", "text": "도나야 음", "addressed": True,
            "context": {"briefing_step": 1, "donna_was_speaking": False, "last_type": "answer"}, "expected_intent": "unknown"}
    (row,) = intent_eval.evaluate([case], ["rule+judge"], post=IntentClova({}))["cases"]
    assert row["intent"] == "unknown" and row["by"] == "heuristic"


# ── 입구 ──


def test_cli_intent_rule_only_runs_without_key(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "clova_studio_api_key", "")
    monkeypatch.setattr(report, "OUT_ROOT", tmp_path / "harness_eval")
    cli.main(["intent", "--systems", "rule"])
    (out,) = (tmp_path / "harness_eval").glob("intent-*/result.json")
    body = json.loads(out.read_text(encoding="utf-8"))
    assert body["suite"] == "intent" and body["systems"] == ["rule"] and body["config"]["data"]["version"] == "intents_v1"
    with pytest.raises(SystemExit):
        cli.main(["intent", "--systems", "A"])
    with pytest.raises(SystemExit):
        cli.main(["intent"])  # rule+judge 는 키가 필요하다


# ── 오발성 세분·호출어 세트 ──


def test_wake_and_addressed_sets_are_unverified_and_balanced(cases):
    body, _ = intent_eval.load_cases()
    assert body["verified_by"] is None  # 사람 확인 전
    wake = [c for c in cases if c["source"] == "wake"]
    assert sum(c["expected_intent"] != "not_for_donna" for c in wake) == 16
    assert sum(c["expected_intent"] == "not_for_donna" for c in wake) == 10
    assert all(not c["addressed"] for c in wake)  # 앱이 호출어를 떼지 못하고 글자 그대로 보낸 말
    addressed = [c for c in cases if c["addressed"]]
    assert len(addressed) >= 10 and all(c["expected_intent"] != "not_for_donna" for c in addressed)
    assert all(c["expected_intent"] != "not_for_donna" for c in cases if c["source"] == "addressed")


def _row(expected, intent, *, addressed=False, source="kitchen", last_type="answer", step=1):
    return {"expected_intent": expected, "intent": intent, "addressed": addressed, "source": source,
            "context": {"briefing_step": step, "donna_was_speaking": False, "last_type": last_type}}


def test_misfire_metrics_split_kitchen_window_addressed_and_wake():
    rows = [
        _row("not_for_donna", "briefing.next"),  # 8초 창 안 주방 대화에 반응
        _row("not_for_donna", "unknown"),  # 못 알아들음은 반응이 아니다
        _row("not_for_donna", "question", last_type=None, step=None),  # 창 밖 (직전 상황 없음)
        _row("not_for_donna", "not_for_donna"),
        _row("question", "not_for_donna", addressed=True, source="addressed"),  # 부른 말 무시
        _row("unknown", "unknown", addressed=True, source="addressed"),
        _row("briefing.next", "briefing.next", source="wake"),
        _row("stop", "not_for_donna", source="wake"),  # 호출어 변형을 놓침
        _row("not_for_donna", "briefing.start", source="wake"),  # 비슷한 말에 반응
        _row("not_for_donna", "not_for_donna", source="wake"),
    ]
    m = {x["id"]: (x["numerator"], x["denominator"]) for x in intent_eval.misfire_metrics("rule", rows)}
    assert m["false_activation_rate"] == (3, 6)
    assert m["window_false_answer_rate"] == (2, 5)
    assert m["missed_command_rate_addressed"] == (1, 2)
    assert m["wake_accept_rate"] == (1, 2)
    assert m["wake_false_accept_rate"] == (1, 2)


def test_old_rows_without_context_use_last_type():
    old = {"expected_intent": "not_for_donna", "intent": "stop", "addressed": False, "source": "kitchen", "last_type": None}
    assert not intent_eval.in_window(old) and intent_eval.in_window({**old, "last_type": "answer"})


def test_dry_run_counts_judge_calls_without_key(tmp_path, monkeypatch, cases):
    monkeypatch.setattr(settings, "clova_studio_api_key", "")
    monkeypatch.setattr(report, "OUT_ROOT", tmp_path / "harness_eval")
    cli.main(["intent", "--dry-run", "--runs", "2"])
    assert not (tmp_path / "harness_eval").exists()
    needed = len(intent_eval.judge_needed(cases))
    assert 0 < needed < len(cases)
    assert intent_eval.planned_calls(cases, ["rule", "rule+judge"], 2) == {
        "rule": {"typical": 0, "max": 0}, "rule+judge": {"typical": needed * 2, "max": needed * 4}}


def test_progress_prints_one_line_per_case_with_calls(monkeypatch):
    monkeypatch.setattr(settings, "clova_studio_api_key", "test-key")
    ctx = {"briefing_step": 1, "donna_was_speaking": False, "last_type": "answer"}
    data = [{"id": "a", "text": "다음", "addressed": False, "context": ctx, "expected_intent": "briefing.next"},
            {"id": "b", "text": "예약 몇 팀이야", "addressed": False, "context": ctx, "expected_intent": "question"}]
    lines = []
    result = intent_eval.evaluate(data, ["rule+judge"], runs=2, post=IntentClova({"예약 몇 팀이야": "not_for_donna"}),
                                  progress=lines.append, prefix="[강도 0] ")
    assert len(lines) == 4 and all(line.startswith("[강도 0] [rule+judge 회차 ") for line in lines)
    assert "1/2 ✓ a \"다음\" → briefing.next rule" in lines[0]
    assert "2/2 ✗ b" in lines[1] and "(정답 question)" in lines[1] and lines[1].endswith("호출 1")
    assert [row["calls"] for row in result["cases"]] == [0, 1, 0, 1]


def test_http_errors_jsonl_keeps_request_shape_not_words(tmp_path, monkeypatch):
    """강제 도구 호출 400 (엄격한 예산이라 다시 묻지 않음): 한 줄. 말 원문·프롬프트는 남기지 않는다."""
    monkeypatch.setattr(settings, "clova_studio_api_key", "test-key")
    ctx = {"briefing_step": 1, "donna_was_speaking": False, "last_type": "answer"}
    case = {"id": "q:1", "text": "그거 저번에 말한 거 있잖아", "addressed": False, "context": ctx, "expected_intent": "unknown"}
    log = tmp_path / "http_errors.jsonl"
    result = intent_eval.evaluate([case], ["rule+judge"], post=IntentClova({}, status=400), error_log=log, log_context={"noise": 2})
    (first,) = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    assert result["http_errors"] == 1 and result["cases"][0]["calls"] == 1
    assert (first["case_id"], first["system"], first["run"], first["noise"], first["status"]) == ("q:1", "rule+judge", 1, 2, 400)
    assert first["tool_choice"] == {"type": "function", "function": {"name": "submit_intent"}}
    assert first["tools"] == ["submit_intent"] and first["roles"] == ["system", "user"]
    assert first["body_keys"] == ["maxTokens", "messages", "temperature", "toolChoice", "tools", "topP"]
    shape = first["tool_shapes"]["submit_intent"]
    assert shape["required"] == ["intent", "owner_said"] and shape["params"]["jump_to"] == {"type": "string", "enum": 5}
    assert first["other"]["temperature"] == 0 and '"400"' in first["response"]
    text = log.read_text(encoding="utf-8")
    assert "저번에" not in text and "직전 상황" not in text  # 말 원문·사용자 메시지·프롬프트는 없다
    ok = intent_eval.evaluate([case], ["rule+judge"], post=IntentClova({}), error_log=tmp_path / "none.jsonl")
    assert ok["http_errors"] == 0 and not (tmp_path / "none.jsonl").exists()  # 실패가 없으면 파일을 만들지 않는다
