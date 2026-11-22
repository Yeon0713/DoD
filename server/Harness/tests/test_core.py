"""하네스 뼈대: CLOVA 도구 호출, 실행 루프, 캐시, 예산, 기록, 근거 대조, 규칙 검사."""

import sqlite3

from app.core import clova_usage_log
from app.core.config import settings
from Harness import cache, clova_tools, guards, runner, trace
from Harness.grounding import Evidence, ungrounded_numbers
from Harness.spec import AgentSpec, Budget, CallBudget, Tool
from Harness.tests.fakes import FakeClova, call
from Harness.tools import obj, string

# ── CLOVA 도구 호출 ──


def test_request_follows_function_calling_rules(make_ctx):
    fake = FakeClova("안녕하세요")
    reply = clova_tools.chat_with_tools(
        [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}], [{"type": "function", "function": {"name": "x"}}],
        feature="t", store_id="t001", max_tokens=300, post=fake,
    )
    body = fake.requests[0]
    assert reply.content == "안녕하세요" and reply.finish_reason == "stop"
    assert body["maxTokens"] == 1024  # 300 을 달라고 해도 하한 1024
    assert body["toolChoice"] == "auto" and body["tools"][0]["function"]["name"] == "x"
    assert all(isinstance(m["content"], str) for m in body["messages"])  # content 는 문자열
    assert "repetitionPenalty" not in body and "stop" not in body
    with sqlite3.connect(clova_usage_log.LOG_PATH) as conn:
        assert conn.execute("SELECT feature, status FROM calls").fetchall() == [("agent:t", "ok")]


def test_arguments_given_as_string_are_read_as_json():
    import httpx

    response = httpx.Response(200, json={"result": {"message": {"content": "", "toolCalls": [
        {"id": "a", "function": {"name": "f", "arguments": '{"date": "2026-11-14"}'}}]}, "finishReason": "tool_calls"}})
    reply = clova_tools.parse_reply(response)
    assert reply.tool_calls[0].arguments == {"date": "2026-11-14"}
    assert reply.as_assistant_message()["toolCalls"][0]["function"]["arguments"] == {"date": "2026-11-14"}


def test_429_waits_and_retries_once(monkeypatch):
    waited = []
    monkeypatch.setattr("Harness.limiter.sleep", waited.append)
    fake = FakeClova(429, "됐어요")
    reply = clova_tools.chat_with_tools([{"role": "user", "content": "u"}], [], feature="t", store_id=None, post=fake)
    assert reply.content == "됐어요" and len(fake.requests) == 2 and waited == [10]


def test_forced_choice_400_retries_with_nudge_then_alt_tools():
    force = {"type": "function", "function": {"name": "x"}}
    tools, alt = [{"type": "function", "function": {"name": "x", "parameters": {"a": 1}}}], [{"type": "function", "function": {"name": "x", "parameters": {"b": 1}}}]
    ask = {"role": "user", "content": "u"}
    # 1) 한 줄 덧붙여 다시 묻기로 해결
    fake = FakeClova(400, [call("x", {})])
    reply = clova_tools.chat_with_tools([ask], tools, feature="t", store_id=None, tool_choice=force, post=fake)
    assert reply.tool_calls[0].name == "x"
    assert [r["toolChoice"] for r in fake.requests] == [force, force]  # auto 로 풀지 않는다
    assert fake.requests[1]["messages"] == [ask, {"role": "user", "content": "답은 반드시 x 도구로 내."}]
    # 2) 그래도 400 이면 다른 모양의 도구로
    fake = FakeClova(400, 400, [call("x", {})])
    reply = clova_tools.chat_with_tools([ask], tools, feature="t", store_id=None, tool_choice=force, post=fake, alt_tools=alt)
    assert reply.tool_calls[0].name == "x" and fake.requests[2]["tools"] == alt and fake.requests[2]["messages"] == [ask]
    # 3) 다 실패하면 None. auto 요청의 400 은 다시 묻지 않는다
    assert clova_tools.chat_with_tools([ask], tools, feature="t", store_id=None, tool_choice=force, post=FakeClova(400, 400, 400), alt_tools=alt) is None
    assert clova_tools.chat_with_tools([], [], feature="t", store_id=None, post=FakeClova(400)) is None


def test_failure_or_no_key_gives_none(monkeypatch):
    assert clova_tools.chat_with_tools([], [], feature="t", store_id=None, post=FakeClova(500)) is None
    monkeypatch.setattr(settings, "clova_studio_api_key", "")
    fake = FakeClova()
    assert clova_tools.chat_with_tools([], [], feature="t", store_id=None, post=fake) is None
    assert fake.requests == []


# ── 실행 루프 ──

ECHO = Tool("get_word", "단어 하나", obj({"key": string("키")}), lambda ctx, task, args: {"word": f"{args['key']}-42"})
SUBMIT = Tool("submit_text", "제출", obj({"text": string("글")}))


def spec(**extra) -> AgentSpec:
    values = dict(
        name="echo",
        system_prompt=lambda task, ctx: "시스템",
        user_message=lambda task, ctx: f"할 일 {task['id']}",
        tools=[ECHO],
        submit=SUBMIT,
        check=lambda args, evidence, task, ctx, notes: "쿠폰은 안 돼요" if "쿠폰" in args["text"] else None,
        task_id=lambda task: task["id"],
        fallback=lambda task, ctx: {"text": "기본 문장"},
    )
    values.update(extra)
    return AgentSpec(**values)


def test_tool_result_goes_back_and_submit_ends_the_run(make_ctx, frozen_clock):
    fake = FakeClova([call("get_word", {"key": "a"})], [call("submit_text", {"text": "a-42 입니다"})])
    proposal = runner.run(spec(), {"id": "T1"}, make_ctx(fake))
    assert proposal.source == "AGENT" and proposal.content == {"text": "a-42 입니다"}
    assert proposal.evidence == ["input", "get_word"]
    tool_msg = [m for m in fake.requests[1]["messages"] if m["role"] == "tool"][0]
    assert tool_msg["toolCallId"] == "call_1" and "a-42" in tool_msg["content"]
    assert fake.requests[0]["messages"][0] == {"role": "system", "content": "시스템"}
    assert sum(m["role"] == "system" for m in fake.requests[1]["messages"]) == 1  # system 메시지는 하나만


def test_rejection_reason_is_fed_back(make_ctx, frozen_clock):
    fake = FakeClova([call("submit_text", {"text": "쿠폰 드려요"})], [call("submit_text", {"text": "고치겠습니다"})])
    proposal = runner.run(spec(), {"id": "T2"}, make_ctx(fake))
    assert proposal.content["text"] == "고치겠습니다"
    assert "거절: 쿠폰은 안 돼요" in fake.tool_messages(1)[0]
    with sqlite3.connect(clova_usage_log.LOG_PATH) as conn:
        assert conn.execute("SELECT verdict, reason FROM calls ORDER BY id").fetchall() == [
            ("rejected", "쿠폰은 안 돼요"), ("accepted", None)]


def test_too_many_rejections_falls_back(make_ctx, frozen_clock):
    fake = FakeClova([call("submit_text", {"text": "쿠폰"})], [call("submit_text", {"text": "쿠폰 또"})])
    proposal = runner.run(spec(), {"id": "T3"}, make_ctx(fake))
    assert proposal.source == "FALLBACK" and proposal.content == {"text": "기본 문장"}
    assert fake.done()


def test_unknown_tool_and_missing_args_are_reported(make_ctx, frozen_clock):
    fake = FakeClova([call("nope", {}), call("get_word", {})], [call("submit_text", {"text": "끝"})])
    runner.run(spec(), {"id": "T4"}, make_ctx(fake))
    first, second = fake.tool_messages(1)
    assert "'nope' 도구는 없어요" in first and "빠진 값이 있어요: key" in second


def test_text_without_tool_is_nudged_once_then_falls_back(make_ctx, frozen_clock):
    fake = FakeClova("그냥 글", "또 글")
    proposal = runner.run(spec(), {"id": "T5"}, make_ctx(fake))
    assert proposal.source == "FALLBACK"
    assert fake.requests[1]["messages"][-1] == {"role": "user", "content": "답은 반드시 submit_text 도구로 제출해 줘."}
    assert fake.requests[0]["toolChoice"] == "auto"
    assert fake.requests[1]["toolChoice"] == {"type": "function", "function": {"name": "submit_text"}}  # 다음엔 제출 강제


def test_repeated_lookup_is_not_rerun_and_forces_submit(make_ctx, frozen_clock):
    runs = []
    counting = Tool("get_word", "단어", obj({"key": string("키")}), lambda ctx, task, args: runs.append(args) or {"word": "x"})
    same = call("get_word", {"key": "a"})
    fake = FakeClova([same], [same], [call("submit_text", {"text": "끝"})])
    proposal = runner.run(spec(tools=[counting]), {"id": "T12"}, make_ctx(fake))
    assert proposal.source == "AGENT" and runs == [{"key": "a"}]  # 같은 조회는 한 번만 실행
    assert "이미 같은 값으로 조회했어요" in fake.tool_messages(2)[-1]
    assert fake.requests[1]["toolChoice"] == "auto" and fake.requests[2]["toolChoice"]["function"]["name"] == "submit_text"


def test_last_step_forces_submit(make_ctx, frozen_clock):
    fake = FakeClova([call("get_word", {"key": "a"})], [call("submit_text", {"text": "끝"})])
    runner.run(spec(budget=Budget(max_steps=2)), {"id": "T13"}, make_ctx(fake))
    assert [r["toolChoice"] for r in fake.requests] == ["auto", {"type": "function", "function": {"name": "submit_text"}}]


def test_step_budget_and_no_fallback_gives_none(make_ctx, frozen_clock):
    fake = FakeClova([call("get_word", {"key": "a"})], [call("get_word", {"key": "b"})])
    assert runner.run(spec(budget=Budget(max_steps=2), fallback=None), {"id": "T6"}, make_ctx(fake)) is None


def test_time_budget(make_ctx, monkeypatch):
    ticks = iter([0.0, 0.0, 99.0])
    monkeypatch.setattr(runner, "clock", lambda: next(ticks))
    fake = FakeClova([call("get_word", {"key": "a"})])
    assert runner.run(spec(budget=Budget(max_seconds=10)), {"id": "T7"}, make_ctx(fake)).source == "FALLBACK"


class TimeoutRecorder(FakeClova):
    """받은 timeout 을 남기는 가짜 CLOVA."""

    def __init__(self, *turns):
        super().__init__(*turns)
        self.timeouts = []

    def __call__(self, url, headers=None, json=None, timeout=None):
        self.timeouts.append(timeout)
        return super().__call__(url, headers=headers, json=json, timeout=timeout)


def test_non_strict_call_timeout_follows_remaining_budget(make_ctx, monkeypatch):
    """엄격하지 않은 예산도 호출 하나의 제한 시간을 남은 시간으로 묶는다 (H7). 재시도 규칙은 그대로."""
    ticks = iter([0.0, 10.0])  # 시작, 1단계 시작(10초 지남)
    monkeypatch.setattr(runner, "clock", lambda: next(ticks))
    fake = TimeoutRecorder([call("submit_text", {"text": "끝"})])
    runner.run(spec(budget=Budget(max_seconds=15)), {"id": "T14"}, make_ctx(fake))
    assert fake.timeouts == [5.0]
    fresh = TimeoutRecorder([call("submit_text", {"text": "끝"})])
    monkeypatch.setattr(runner, "clock", lambda: 0.0)
    runner.run(spec(), {"id": "T15"}, make_ctx(fresh))
    assert fresh.timeouts == [20]  # 남은 시간이 넉넉하면 기본 제한 시간 그대로


def test_worker_uses_earlier_parent_deadline(make_ctx, frozen_clock):
    """부모(supervisor) 마감이 더 이르면 그 마감까지만 쓴다 (H7)."""
    fake = TimeoutRecorder([call("submit_text", {"text": "끝"})])
    runner.run(spec(), {"id": "T16"}, make_ctx(fake, deadline=3.0))
    assert fake.timeouts == [3.0]


def test_fallback_can_be_skipped_after_deadline(make_ctx, monkeypatch):
    """fallback_after_deadline=False 면 마감이 지난 뒤 물러나기 호출을 하지 않는다. 기본(True)은 그대로 물러난다 (H7)."""
    called = []
    ticks = iter([0.0, 0.0, 99.0, 99.0])  # 시작, 1단계, 2단계(시간 초과), 물러나기 전 확인
    monkeypatch.setattr(runner, "clock", lambda: next(ticks))
    late = spec(budget=Budget(max_seconds=10), fallback=lambda task, ctx: called.append(task) or {"text": "기본 문장"},
                fallback_after_deadline=False)
    assert runner.run(late, {"id": "T17"}, make_ctx(FakeClova([call("get_word", {"key": "a"})]))) is None
    assert called == []


def test_shared_call_budget_stops_before_calling(make_ctx, frozen_clock):
    fake = FakeClova()
    proposal = runner.run(spec(), {"id": "T8"}, make_ctx(fake, call_budget=CallBudget(0)))
    assert proposal.source == "FALLBACK" and fake.requests == []


def test_cache_hit_skips_clova_and_fallbacks_are_not_cached(make_ctx, frozen_clock):
    fake = FakeClova([call("submit_text", {"text": "좋아요"})])
    first = runner.run(spec(), {"id": "T9"}, make_ctx(fake))
    again = runner.run(spec(), {"id": "T9"}, make_ctx(FakeClova()))
    assert again is first
    failing = FakeClova(500, 500)
    runner.run(spec(), {"id": "T10"}, make_ctx(failing))
    runner.run(spec(), {"id": "T10"}, make_ctx(failing))
    assert len(failing.requests) == 2  # 물러나기 결과는 기억하지 않아 다시 시도한다


def test_cache_scope_none_keeps_old_key(make_ctx):
    """cache_scope 가 없는 스펙(음성 서버 에이전트들)은 예전과 같은 입력 해시를 쓴다 (H2: 디스크 캐시가 빗나가지 않게)."""
    ctx = make_ctx(FakeClova())
    key = runner.cache_key(spec(), {"id": "T1"}, ctx, "시스템", "할 일 T1")
    assert key[2] == cache.digest(["할 일 T1", []])
    scoped = runner.cache_key(spec(cache_scope=lambda task: task["id"]), {"id": "T1"}, ctx, "시스템", "할 일 T1")
    assert scoped[2] == cache.digest(["할 일 T1", [], "T1"]) and scoped[2] != key[2]


def test_trace_records_each_step(make_ctx, frozen_clock):
    ctx = make_ctx(FakeClova([call("get_word", {"key": "a"})], [call("submit_text", {"text": "끝"})]))
    runner.run(spec(), {"id": "T11"}, ctx)
    kinds = [(s["step"], s["kind"], s["name"]) for s in trace.steps_of(ctx.run_id)]
    assert kinds == [(0, "start", "T11"), (1, "llm", "tool_calls"), (1, "tool", "get_word"), (2, "llm", "tool_calls"),
                     (2, "submit", "submit_text"), (2, "end", "accepted")]


def test_trace_failure_does_not_break_the_run(make_ctx, frozen_clock, monkeypatch):
    """실행 기록 DB 가 잠기거나 망가져도 에이전트 실행은 그대로 끝난다 (H5)."""
    def locked():
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(trace, "_db", locked)
    fake = FakeClova([call("get_word", {"key": "a"})], [call("submit_text", {"text": "a-42 입니다"})])
    proposal = runner.run(spec(), {"id": "T18"}, make_ctx(fake))
    assert proposal.source == "AGENT" and proposal.content == {"text": "a-42 입니다"}


def test_trace_uses_wal():
    """읽기(대시보드)와 쓰기가 서로 막지 않게 WAL 로 쓴다 (H5)."""
    trace.record(run_id="r", parent_run_id=None, agent="echo", store_id="t001", step=0, kind="start", name="T")
    with sqlite3.connect(trace.TRACE_PATH) as conn:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"


def test_record_without_limit_keeps_full_text():
    """limit=None 이면 detail 을 자르지 않는다 (H10)."""
    trace.record(run_id="r", parent_run_id=None, agent="echo", store_id="t001", step=0, kind="start", name="T",
                 detail="x" * 10000, limit=None)
    assert len(trace.steps_of("r")[0]["detail"]) == 10000


# ── 근거 대조와 규칙 검사 ──


def test_numbers_must_come_from_evidence():
    evidence = Evidence(["최근 7일"])
    evidence.add("tool", {"hour": "19시(오후 7시)", "times_usual": 1.8})
    assert ungrounded_numbers("최근 7일 오후 7시 주문이 평소의 1.8배예요", evidence) == []
    assert ungrounded_numbers("평소의 2배예요", evidence) == ["2"]


def test_old_regex_rules_miss_meaning_so_they_become_hints():
    # 보상 정규식은 '환불은 어렵다'를 보상 약속으로 잡고, '한 그릇 더 넣어 드릴게요'는 놓친다 → 보상은 판별기가 따로 본다
    assert guards.PROMISE_RE.search("환불은 고객센터에서만 가능해서 저희가 처리하긴 어려워요")
    assert not guards.PROMISE_RE.search("다음 주문 땐 면 한 그릇 더 넣어 드릴게요")
    assert guards.hint_phrases("환불은 고객센터에서만 가능해서 저희가 처리하긴 어려워요") == []  # 검토 힌트에는 보상을 넣지 않는다


def test_price_and_numbers_kept():
    assert guards.price_or_discount("오늘만 20% 할인") is not None
    assert guards.price_or_discount("따끈한 국수 한 그릇") is None
    assert guards.numbers_kept("12월부터 033-123-4567", "12월부터 연락은 033-123-4567") is None
    assert guards.numbers_kept("12월부터", "겨울부터") is not None
