"""guards 의 429 대응: 헤더를 따라 기다리기, 이어 돌릴 때 429·시간 초과 줄 다시 판정, 판정기별 동시 호출. 가짜 CLOVA 만."""


import httpx
import pytest

from app.core.config import settings
from Harness import clova_tools, limiter
from Harness.evals import cli, guards_eval, judge
from Harness.tests.fakes import FakeClova


@pytest.fixture(autouse=True)
def fresh_limits(monkeypatch):
    monkeypatch.setattr(limiter, "rate_limit_stats", {"waits": 0, "seconds": 0.0})
    monkeypatch.setattr(limiter, "first_rate_limit_headers", None)
    judge.reset_model_errors()
    yield
    judge.reset_model_errors()


# ── 헤더를 따라 기다리기 ──


@pytest.mark.parametrize("headers, seconds", [
    ({"Retry-After": "7"}, 7),
    ({"x-ratelimit-reset-requests": "1m2s", "x-ratelimit-limit-requests": "60"}, 60),  # 상한 60초
    ({"x-ratelimit-reset-requests": "12s", "x-ratelimit-reset-tokens": "500ms"}, 12),
    ({"x-ratelimit-reset-tokens": "1.5"}, 1.5),
    ({}, limiter.RATE_LIMIT_WAIT_SECONDS),
    ({"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"}, limiter.RATE_LIMIT_WAIT_SECONDS),  # 날짜 모양은 못 읽어 기본값
])
def test_wait_seconds_follow_headers(headers, seconds):
    assert limiter.wait_seconds(headers) == seconds


def test_429_waits_by_header_counts_and_prints_headers_once(monkeypatch, capsys):
    waited = []
    monkeypatch.setattr(limiter, "sleep", waited.append)
    monkeypatch.setattr(limiter, "RATE_LIMIT_RETRIES", 3)
    headers = {"x-ratelimit-limit-requests": "60", "x-ratelimit-remaining-requests": "0", "Retry-After": "3", "x-other": "1"}
    calls = []

    def post(url, **kwargs):
        calls.append(kwargs["json"])
        if len(calls) <= 2:
            return httpx.Response(429, headers=headers, json={"status": {"code": "42901"}}, request=httpx.Request("POST", url))
        return FakeClova("됐어요")(url, **kwargs)

    reply = clova_tools.chat_with_tools([{"role": "user", "content": "u"}], [], feature="t", store_id=None, post=post)
    assert reply.content == "됐어요" and waited == [3, 3]
    assert limiter.rate_limit_snapshot() == {"waits": 2, "seconds": 6.0}
    assert limiter.first_rate_limit_headers == {"x-ratelimit-limit-requests": "60", "x-ratelimit-remaining-requests": "0",
                                                "retry-after": "3"}
    out = capsys.readouterr().out
    assert out.count("[429] CLOVA 한도 헤더") == 1 and "x-ratelimit-limit-requests" in out


def test_judge_vote_error_names_http_status(monkeypatch, tmp_path):
    from app.core import clova_usage_log

    monkeypatch.setattr(clova_usage_log, "LOG_PATH", tmp_path / "clova_usage.db")
    monkeypatch.setattr(settings, "clova_studio_api_key", "test-key")
    monkeypatch.setattr(limiter, "sleep", lambda s: None)
    monkeypatch.setattr(limiter, "RATE_LIMIT_RETRIES", 0)

    def busy(url, **kwargs):
        return httpx.Response(429, json={"status": {"code": "42901"}}, request=httpx.Request("POST", url))

    data = judge.JudgeInput(review_text="맛있어요", reply="감사합니다 또 오세요", category="국수", sentiment="POSITIVE",
                            complaint_types=[], menus=[], store_facts=[])
    verdict = judge.judge("policy", data, mode="thinking", votes=1, post=busy)
    assert verdict.votes[0].error == "호출 실패 (HTTP 429)"


# ── 이어 돌릴 때 다시 판정할 줄 ──


def thinking_row(case_id, errors, outcome="unknown", error="판단 불가 조건이 있음"):
    return {"system": "judge_thinking", "run": 1, "case_id": case_id, "outcome": outcome, "error": error,
            "verdicts": {"fact": {"vote": [None], "ok": None, "errors": errors}}}


def test_retryable_rows():
    assert guards_eval.retryable(thinking_row("old", ["호출 실패", "호출 실패"]))  # 예전 기록 (까닭 없음)
    assert guards_eval.retryable(thinking_row("r429", ["호출 실패 (HTTP 429)"]))
    assert guards_eval.retryable(thinking_row("r503", ["호출 실패 (HTTP 503)"]))
    assert guards_eval.retryable(thinking_row("net", ["호출 실패 (연결·시간 초과)"]))
    assert guards_eval.retryable(thinking_row("late", [], error="사례 제한 시간 900초를 넘김"))
    assert not guards_eval.retryable(thinking_row("shape", ["JSON 이 아니에요"]))  # 모델 답이 틀린 것은 그대로
    assert not guards_eval.retryable(thinking_row("bad", ["호출 실패 (HTTP 400)"]))
    assert not guards_eval.retryable(thinking_row("done", ["호출 실패 (HTTP 429)"], outcome="caught", error=None))


def test_resumable_drops_429_rows():
    rows = [thinking_row("a", ["호출 실패 (HTTP 429)"]), thinking_row("b", ["JSON 이 아니에요"]),
            {"system": "judge_thinking", "run": 1, "case_id": "c", "outcome": "pass", "error": None, "verdicts": {}}]
    assert {row["case_id"] for row in guards_eval.resumable(rows)} == {"b", "c"}


# ── 판정기별 동시 호출 ──


def test_parse_system_concurrency():
    names = ["regex", "judge_tools", "judge_thinking"]
    assert guards_eval.parse_system_concurrency("judge_thinking=1", names, 2) == {"regex": 2, "judge_tools": 2, "judge_thinking": 1}
    with pytest.raises(guards_eval.JudgeUnavailable, match="--system-concurrency"):
        guards_eval.parse_system_concurrency("judge_thinking=0", names, 2)
    with pytest.raises(guards_eval.JudgeUnavailable):
        guards_eval.parse_system_concurrency("critic=1", names, 2)


def test_evaluate_sets_limit_per_system_and_restores(monkeypatch):
    seen = []
    monkeypatch.setitem(guards_eval.RUNNERS, "critic", lambda case, store, post: (
        seen.append(("critic", limiter.MAX_CONCURRENT)) or guards_eval.Judgement(ok=True)))
    monkeypatch.setitem(guards_eval.RUNNERS, "judge_thinking", lambda case, store, post: (
        seen.append(("judge_thinking", limiter.MAX_CONCURRENT)) or guards_eval.Judgement(ok=True)))
    before = limiter.MAX_CONCURRENT
    cases = guards_eval.critic_cases()[:2]
    stores = {"t001": guards_eval.critic_store()}
    guards_eval.evaluate(cases, stores, ["critic", "judge_thinking"], workers=4, concurrency={"critic": 3, "judge_thinking": 1})
    assert set(seen) == {("critic", 3), ("judge_thinking", 1)} and limiter.MAX_CONCURRENT == before


def test_judge_thinking_gets_longer_case_deadline(monkeypatch):
    made = []
    real = guards_eval.GuardedPost

    def spy(post=None, **kwargs):
        made.append(kwargs.get("deadline"))
        return real(post, **kwargs)

    monkeypatch.setattr(guards_eval, "GuardedPost", spy)
    monkeypatch.setitem(guards_eval.RUNNERS, "judge_thinking", lambda case, store, post: guards_eval.Judgement(ok=True))
    monkeypatch.setitem(guards_eval.RUNNERS, "critic", lambda case, store, post: guards_eval.Judgement(ok=True))
    case = guards_eval.critic_cases()[0]
    store = guards_eval.critic_store()
    guards_eval.timed("judge_thinking", case, store)
    guards_eval.timed("critic", case, store)
    assert made == [900, guards_eval.CASE_DEADLINE_SECONDS]


def test_cli_dry_run_shows_concurrency_per_system(tmp_path, capsys):
    from Harness.tests.fake_gold import write_gold

    pytest.importorskip("openpyxl")
    path, sha = write_gold(tmp_path / "gold.xlsx")
    cli.main(["guards", "--systems", "regex,judge_tools,judge_thinking", "--system-concurrency", "judge_thinking=1",
              "--concurrency", "2", "--dry-run", "--gold", str(path), "--gold-sha", sha])
    out = capsys.readouterr().out
    assert "CLOVA 동시 호출 judge_tools 2, judge_thinking 1" in out
    with pytest.raises(SystemExit):
        cli.main(["guards", "--systems", "regex", "--system-concurrency", "judge_thinking=1", "--dry-run",
                  "--gold", str(path), "--gold-sha", sha])
