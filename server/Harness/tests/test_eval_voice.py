"""voice 스위트(Harness/evals/voice_eval.py): /v1/turn 종류별 응답 시간. 가짜 CLOVA·가짜 시계로만 본다."""

import json
import os

import pytest

from app.core.config import settings
from Harness.evals import cli, metrics, report, voice_eval
from Harness.tests.test_eval_intent import IntentClova


class Clock:
    """voice_eval.timer 자리. CLOVA 를 부를 때만 시간이 간다 (나머지 말은 0초)."""

    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


class SlowClova(IntentClova):
    def __init__(self, clock: Clock, seconds: float, answers: dict | None = None):
        super().__init__(answers or {}, default="question")
        self.clock, self.seconds = clock, seconds

    def __call__(self, url, **kwargs):
        self.clock.now += self.seconds
        return super().__call__(url, **kwargs)


def no_clova(*args, **kwargs):
    raise AssertionError("rule 은 CLOVA 를 부르면 안 돼요")


def kinds():
    return {kind: sum(1 for _, k, _ in voice_eval.TURNS if k == kind) for kind in voice_eval.TARGETS}


def test_script_covers_briefing_steps_questions_and_kitchen():
    texts = [text for text, _, _ in voice_eval.TURNS]
    assert kinds() == {"briefing": 11, "question": 10, "kitchen": 3}
    assert None in texts  # auto_next
    for word in ("브리핑", "다음", "다시 말해", "보여", "읽어", "돌아가기", "처음부터", "그만"):
        assert any(text and word in text for text in texts), word
    assert voice_eval.likely_judge_turns()  # 판정 에이전트로 가는 말이 있다


def test_rule_system_never_calls_clova_and_restores_state(tmp_path, monkeypatch):
    from voice import config, context, tts

    monkeypatch.setattr(voice_eval, "timer", Clock())
    before = (config.DB_PATH, tts.ENABLED, context.post, os.environ.get("VOICE_AGENT_INTENT"))
    result = voice_eval.evaluate(["rule"], runs=2, out=tmp_path, post=no_clova)
    assert (config.DB_PATH, tts.ENABLED, context.post, os.environ.get("VOICE_AGENT_INTENT")) == before
    assert (tmp_path / "voice.db").exists()
    rows = result["cases"]
    assert len(rows) == 2 * len(voice_eval.TURNS) and result["calls"] == 0
    assert all(row["status"] == 200 and row["error"] is None for row in rows), [r for r in rows if r["error"]]
    first = [row for row in rows if row["run"] == 1]
    assert (first[0]["intent"], first[0]["type"]) == ("briefing.start", "answer")
    assert first[1]["type"] == "ignore"  # 주방 대화
    m = {x["id"]: x for x in result["metrics"]}
    for kind, count in kinds().items():
        assert (m[f"turn_within_target:{kind}"]["numerator"], m[f"turn_within_target:{kind}"]["denominator"]) == (2 * count,) * 2
        assert m[f"turn_p95:{kind}"]["value"] == 0.0
    assert m["turn_over_timeout_rate"]["numerator"] == 0 and m["turn_judge_within_budget"]["denominator"] == 0


@pytest.mark.parametrize("seconds, within_budget, over_timeout", [(2.0, True, False), (4.0, False, False), (6.0, False, True)])
def test_judge_turns_are_timed_against_targets(tmp_path, monkeypatch, seconds, within_budget, over_timeout):
    monkeypatch.setattr(settings, "clova_studio_api_key", "test-key")
    clock = Clock()
    monkeypatch.setattr(voice_eval, "timer", clock)
    post = SlowClova(clock, seconds)
    result = voice_eval.evaluate(["rule+judge"], out=tmp_path, post=post)
    rows = result["cases"]
    judged = [row for row in rows if row["calls"]]
    assert judged and result["calls"] == len(post.requests) == sum(row["calls"] for row in rows)
    assert all(row["seconds"] == seconds for row in judged)
    assert all(row["seconds"] == 0.0 for row in rows if not row["calls"])
    m = {x["id"]: x for x in result["metrics"]}
    slow_questions = sum(1 for row in judged if row["kind"] == "question")
    q = m["turn_within_target:question"]
    assert q["numerator"] == q["denominator"] - (0 if seconds <= 3 else slow_questions)
    assert m["turn_judge_within_budget"]["numerator"] == (len(judged) if within_budget else 0)
    assert m["turn_over_timeout_rate"]["numerator"] == (len(judged) if over_timeout else 0)
    assert m["turn_clova_calls"]["value"] == len(post.requests)


def test_server_error_counts_as_timeout(tmp_path, monkeypatch):
    from voice.dialog import turn

    monkeypatch.setattr(voice_eval, "timer", Clock())
    original = turn.dispatch

    def broken(intent, session, brief, view):
        if intent.name == "briefing.repeat":
            raise RuntimeError("고장")
        return original(intent, session, brief, view)

    monkeypatch.setattr(turn, "dispatch", broken)
    result = voice_eval.evaluate(["rule"], out=tmp_path, post=no_clova)
    (bad,) = [row for row in result["cases"] if row["error"]]
    assert bad["text"] == "다시 말해 줘" and bad["status"] == 500
    m = {x["id"]: x for x in result["metrics"]}
    assert m["turn_over_timeout_rate"]["numerator"] == 1
    assert m["turn_within_target:briefing"]["numerator"] == m["turn_within_target:briefing"]["denominator"] - 1


def test_percentile_nearest_rank():
    assert metrics.percentile([], 95) is None
    assert metrics.percentile([3.0, 1.0, 2.0], 50) == 2.0
    assert metrics.percentile([float(n) for n in range(1, 21)], 95) == 19.0
    assert metrics.percentile([0.5], 95) == 0.5


def test_cli_voice(tmp_path, monkeypatch):
    monkeypatch.setattr(report, "OUT_ROOT", tmp_path / "harness_eval")
    monkeypatch.setattr(voice_eval, "timer", Clock())
    monkeypatch.setattr(settings, "clova_studio_api_key", "")
    monkeypatch.setattr(voice_eval.httpx, "post", no_clova)
    cli.main(["voice", "--dry-run"])
    assert not (tmp_path / "harness_eval").exists()
    with pytest.raises(SystemExit):
        cli.main(["voice"])  # 기본 rule+judge 는 키가 필요하다
    with pytest.raises(SystemExit):
        cli.main(["voice", "--systems", "A"])
    cli.main(["voice", "--systems", "rule"])
    (out,) = (tmp_path / "harness_eval").glob("voice-*/result.json")
    body = json.loads(out.read_text(encoding="utf-8"))
    assert body["suite"] == "voice" and body["systems"] == ["rule"] and body["config"]["targets"]["briefing"] == 1.0
    assert (out.parent / "voice.db").exists()  # 저장소는 결과 폴더에


def test_progress_prints_each_turn_and_marks_late(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "clova_studio_api_key", "test-key")
    clock = Clock()
    monkeypatch.setattr(voice_eval, "timer", clock)
    lines = []
    voice_eval.evaluate(["rule+judge"], runs=1, out=tmp_path, post=SlowClova(clock, 4.0), progress=lines.append)
    assert len(lines) == len(voice_eval.TURNS) and lines[0].startswith(f"[rule+judge 회차 1/1] 1/{len(voice_eval.TURNS)} ✓ briefing")
    slow = [line for line in lines if "호출 1" in line]
    assert slow and all("4.00초" in line for line in slow)
    assert all(" ✗ question" in line for line in slow if " question " in line)  # 질문 목표 3초를 넘김


def test_http_errors_jsonl_names_the_turn(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "clova_studio_api_key", "test-key")
    monkeypatch.setattr(voice_eval, "timer", Clock())
    log = tmp_path / "http_errors.jsonl"
    result = voice_eval.evaluate(["rule+judge"], out=tmp_path, post=IntentClova({}, status=400), error_log=log)
    rows = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    judged = [row for row in result["cases"] if row["calls"]]
    assert result["http_errors"] == len(rows) == sum(row["calls"] for row in judged)
    assert {row["case_id"] for row in rows} == {r["case_id"] for r in judged} and all(r["system"] == "rule+judge" for r in rows)
    assert {row["kind"] for row in rows} <= {"question", "kitchen"}
    assert all(text not in log.read_text(encoding="utf-8") for text, _, _ in voice_eval.TURNS if text)


def test_timeout_fallback_is_counted_in_intent_and_voice(monkeypatch, tmp_path):
    """예산 초과로 어림짐작으로 넘어간 것: http_errors.jsonl 에 status timeout 한 줄, 지표 judge_timeout_fallback_rate."""
    from Harness import limiter, runner
    from Harness.evals import intent_eval
    from Harness.tests.test_strict_budget import Clock as BudgetClock, SlowClova as BudgetClova

    clock = BudgetClock()
    monkeypatch.setattr(runner, "clock", clock)
    monkeypatch.setattr(limiter, "wait_after_429", lambda headers: 0.0)
    SlowClova = BudgetClova  # noqa: N806
    monkeypatch.setattr(settings, "clova_studio_api_key", "test-key")
    ctx = {"briefing_step": 1, "donna_was_speaking": False, "last_type": "answer"}
    cases = [{"id": "s", "text": "그거 저번에 말한 거 있잖아", "addressed": False, "context": ctx, "expected_intent": "unknown"}]
    log = tmp_path / "intent_errors.jsonl"
    result = intent_eval.evaluate(cases, ["rule+judge"], post=SlowClova(clock, 10.0), error_log=log)
    m = {x["id"]: x for x in result["metrics"]}
    assert (m["judge_timeout_fallback_rate"]["numerator"], m["judge_timeout_fallback_rate"]["denominator"]) == (1, 1)
    assert m["judge_fallback_rate"]["numerator"] == 1 and result["cases"][0]["judge_timeout"] is True
    (row,) = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    assert row["status"] == "timeout" and row["timeout_limit"] == pytest.approx(3.0) and row["case_id"] == "s"
    ok = intent_eval.evaluate(cases, ["rule+judge"], post=SlowClova(clock, 1.0))
    assert {x["id"]: x for x in ok["metrics"]}["judge_timeout_fallback_rate"]["numerator"] == 0

    monkeypatch.setattr(voice_eval, "timer", clock)
    voice = voice_eval.evaluate(["rule+judge"], out=tmp_path, post=SlowClova(clock, 10.0), error_log=tmp_path / "v.jsonl")
    judged = [row for row in voice["cases"] if row["calls"]]
    vm = {x["id"]: x for x in voice["metrics"]}
    assert judged and all(row["judge_timeout"] for row in judged) and all(row["seconds"] <= 3.0 + 1e-9 for row in judged)
    assert (vm["turn_judge_timeout_rate"]["numerator"], vm["turn_judge_timeout_rate"]["denominator"]) == (len(judged), len(judged))
    assert vm["turn_over_timeout_rate"]["numerator"] == 0  # 앱 5초 초과 없음
