"""엄격한 예산(Budget.strict): 음성 뜻 판정(intent_judge)은 3초를 넘기지 않는다. 가짜 CLOVA·가짜 시계로만 본다.

호출 제한 시간 = 남은 예산, 429·강제 제출 400 에 다시 묻지 않는다. 다른 에이전트(strict=False)는 예전처럼 다시 묻는다.
"""

import httpx
import pytest

from Harness import clova_tools, limiter, runner
from Harness.evals import intent_eval
from voice import context
from voice.agents import intent_judge


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


class SlowClova:
    """latency 초 걸리는 CLOVA. 받은 timeout 보다 길면 그만큼 기다린 뒤 시간 초과를 낸다. status 는 응답 차례."""

    def __init__(self, clock: Clock, latency: float, statuses=(200,)):
        self.clock, self.latency, self.statuses = clock, latency, list(statuses)
        self.timeouts = []

    def __call__(self, url, headers=None, json=None, timeout=None):
        self.timeouts.append(timeout)
        if timeout is not None and self.latency > timeout:
            self.clock.now += timeout
            raise httpx.ReadTimeout("시간 초과", request=httpx.Request("POST", url))
        self.clock.now += self.latency
        status = self.statuses.pop(0) if len(self.statuses) > 1 else self.statuses[0]
        if status != 200:
            return httpx.Response(status, json={"status": {"code": "40009" if status == 400 else str(status)}},
                                  headers={"retry-after": "10"}, request=httpx.Request("POST", url))
        message = {"role": "assistant", "content": "", "toolCalls": [{"id": "c1", "type": "function", "function": {
            "name": "submit_intent", "arguments": {"intent": "question", "owner_said": "오늘 바쁠까"}}}]}
        return httpx.Response(200, json={"status": {"code": "20000"}, "result": {"message": message, "finishReason": "tool_calls"}},
                              request=httpx.Request("POST", url))


@pytest.fixture
def clock(monkeypatch):
    fake = Clock()
    monkeypatch.setattr(runner, "clock", fake)
    waits = []
    monkeypatch.setattr(limiter, "wait_after_429", lambda headers: waits.append(headers) or 10.0)
    fake.waits = waits
    return fake


def judge(post, monkeypatch):
    monkeypatch.setattr(context, "post", post)
    return intent_judge.judge(intent_eval.make_view(), "오늘 바쁠까", "도나가 브리핑 중이에요")


def test_intent_judge_is_strict():
    assert intent_judge.SPEC.budget.strict is True and intent_judge.SPEC.budget.max_seconds == 3


def test_forced_400_is_not_retried(clock, monkeypatch):
    post = SlowClova(clock, 2.6, statuses=(400,))
    assert judge(post, monkeypatch) is None
    assert len(post.timeouts) == 1 and clock.now == pytest.approx(2.6)  # 예전에는 다시 물어 5.2초


def test_429_is_not_waited_for(clock, monkeypatch):
    post = SlowClova(clock, 0.4, statuses=(429, 200))
    assert judge(post, monkeypatch) is None
    assert len(post.timeouts) == 1 and clock.waits == []  # 기다렸다 다시 부르지 않는다


def test_slow_call_is_cut_at_the_remaining_budget(clock, monkeypatch):
    post = SlowClova(clock, 10.0)
    assert judge(post, monkeypatch) is None
    assert post.timeouts == [pytest.approx(3.0)] and clock.now <= 3.0  # 최악 3초 안


def test_timeout_uses_what_is_left_and_a_floor(clock, monkeypatch):
    clock.now = 0.0
    start = clock.now
    post = SlowClova(clock, 1.0)
    assert judge(post, monkeypatch)["intent"] == "question" and post.timeouts == [pytest.approx(3.0 - (clock.now - 1.0 - start))]
    spec = intent_judge.SPEC
    late = max(runner.MIN_CALL_SECONDS, spec.budget.max_seconds - 2.9)
    assert late == runner.MIN_CALL_SECONDS


def test_non_strict_agents_still_retry_forced_400(monkeypatch):
    clock = Clock()
    post = SlowClova(clock, 0.1, statuses=(400, 400))
    tools = intent_judge.SPEC.tool_schemas()
    reply = clova_tools.chat_with_tools([{"role": "user", "content": "x"}], tools, feature="t", store_id=None,
                                        tool_choice={"type": "function", "function": {"name": "submit_intent"}}, post=post)
    assert reply is None and len(post.timeouts) == 2 and post.timeouts[0] == 20  # 기본 제한 시간, 다시 묻기 한 번



# ── 자리(동시 호출 한도) 기다리기 (H4): 실제 시간으로 기다리므로 시간은 작게 둔다 ──

ASK = [{"role": "user", "content": "x"}]


def test_strict_call_does_not_wait_forever_for_a_slot(monkeypatch):
    import threading
    import time

    from Harness.tests.fakes import FakeClova

    monkeypatch.setattr(limiter, "_semaphore", threading.BoundedSemaphore(1))
    limiter._semaphore.acquire()  # 다른 백그라운드 에이전트가 자리를 잡고 있다
    fake = FakeClova("됐어요")
    started = time.perf_counter()
    try:
        reply = clova_tools.chat_with_tools(ASK, [], feature="t", store_id=None, timeout=0.2, retry=False, post=fake)
    finally:
        limiter._semaphore.release()
    assert reply is None and fake.requests == [] and time.perf_counter() - started < 0.5


def test_strict_call_subtracts_slot_wait_from_http_timeout(monkeypatch):
    import threading

    monkeypatch.setattr(limiter, "_semaphore", threading.BoundedSemaphore(1))
    limiter._semaphore.acquire()
    threading.Timer(0.2, limiter._semaphore.release).start()  # 0.2초 뒤 자리가 난다
    post = SlowClova(Clock(), 0.0)
    clova_tools.chat_with_tools(ASK, [], feature="t", store_id=None, timeout=1.0, retry=False, post=post)
    assert len(post.timeouts) == 1 and 0.5 <= post.timeouts[0] <= 0.85  # 기다린 만큼 뺀다


def test_non_strict_still_waits(monkeypatch):
    import threading

    from Harness.tests.fakes import FakeClova

    monkeypatch.setattr(limiter, "_semaphore", threading.BoundedSemaphore(1))
    limiter._semaphore.acquire()
    threading.Timer(0.1, limiter._semaphore.release).start()
    fake = FakeClova("됐어요")
    reply = clova_tools.chat_with_tools(ASK, [], feature="t", store_id=None, timeout=0.2, retry=True, post=fake)
    assert reply.content == "됐어요" and len(fake.requests) == 1
