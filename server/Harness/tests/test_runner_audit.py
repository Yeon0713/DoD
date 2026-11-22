"""실행 틀의 2차 감사 자리 (Harness/spec.py AgentSpec.audit, runner.run). 감사팀 계획 8-1, 16장 3단계."""

import dataclasses

from Harness import cache, runner, trace
from Harness.spec import AgentSpec, AuditVerdict, Budget, Tool
from Harness.tests.fakes import FakeClova, call
from Harness.tools import obj, string

SUBMIT = Tool("submit_text", "글을 낸다", obj({"text": string("글")}))


def spec(audit=None, check=None, **kw) -> AgentSpec:
    return AgentSpec(
        name="t_agent", system_prompt=lambda t, c: "s", user_message=lambda t, c: f"u {t['id']}", tools=[], submit=SUBMIT,
        check=check or (lambda args, ev, t, c, notes: None), task_id=lambda t: t["id"], audit=audit,
        budget=kw.pop("budget", Budget(max_steps=3, max_rejections=2, max_seconds=40)), **kw)


def judge(*statuses):
    """차례대로 판정하는 가짜 감사. 부른 인자를 seen 에 남긴다."""
    queue = list(statuses)

    def audit(args, evidence, task, ctx):
        audit.seen.append(args["text"])
        status = queue.pop(0)
        return AuditVerdict(status, reason=f"지적{len(audit.seen)}" if status == "fail" else None,
                            detail={"criterion": "c" if status == "fail" else None, "quotes": [], "calls": 1})

    audit.seen = []
    return audit


def submit(text):
    return [call("submit_text", {"text": text})]


def test_no_audit_is_unchanged(make_ctx, frozen_clock):
    fake = FakeClova(submit("가"))
    proposal = runner.run(spec(), {"id": "1"}, make_ctx(fake))
    assert proposal.content == {"text": "가"} and proposal.audit is None and len(fake.requests) == 1


def test_one_fail_then_pass_in_same_conversation(make_ctx, frozen_clock):
    audit = judge("fail", "pass")
    fake = FakeClova(submit("가"), submit("나"))
    proposal = runner.run(spec(audit), {"id": "2"}, make_ctx(fake))
    assert proposal.content == {"text": "나"} and audit.seen == ["가", "나"]
    assert fake.tool_messages(1)[0].startswith("감사팀 지적: 지적1")
    assert proposal.audit["passed"] is True and proposal.audit["rounds"] == 1 and proposal.audit["reasons"] == ["지적1"]
    assert [t["status"] for t in proposal.audit["trail"]] == ["fail", "pass"]
    assert cache.get(runner.cache_key(spec(audit), {"id": "2"}, make_ctx(fake), "s", "u 2")) is proposal


def test_three_fails_return_failed_and_not_cached(make_ctx, frozen_clock):
    audit = judge("fail", "fail", "fail")
    fake = FakeClova(submit("가"), submit("나"), submit("다"))
    proposal = runner.run(spec(audit), {"id": "3"}, make_ctx(fake))
    assert proposal.content == {"text": "다"} and proposal.source == "AGENT"
    assert proposal.audit["passed"] is False and proposal.audit["rounds"] == 2
    assert cache.get(runner.cache_key(spec(audit), {"id": "3"}, make_ctx(fake), "s", "u 3")) is None


def test_unchecked_is_none_without_return(make_ctx, frozen_clock):
    fake = FakeClova(submit("가"))
    proposal = runner.run(spec(judge("unchecked")), {"id": "4"}, make_ctx(fake))
    assert proposal.audit["passed"] is None and proposal.audit["rounds"] == 0


def test_audit_error_is_unchecked(make_ctx, frozen_clock):
    def broken(args, evidence, task, ctx):
        raise RuntimeError("터짐")

    proposal = runner.run(spec(broken), {"id": "4b"}, make_ctx(FakeClova(submit("가"))))
    assert proposal.audit["passed"] is None and proposal.audit["trail"][0]["criterion"] == "error"


def test_code_reject_after_return_counts_only_rejections(make_ctx, frozen_clock):
    def check(args, ev, t, c, notes):
        return "짧아요" if args["text"] == "x" else None

    audit = judge("fail", "pass")
    fake = FakeClova(submit("가"), submit("x"), submit("나"))
    proposal = runner.run(spec(audit, check), {"id": "5"}, make_ctx(fake))
    assert proposal.content == {"text": "나"} and audit.seen == ["가", "나"]  # 1차에 걸린 제출은 감사하지 않는다
    assert fake.tool_messages(2)[-1].startswith("거절: 짧아요")
    assert proposal.audit["rounds"] == 1


def test_returns_add_steps_and_last_step_forces_submit(make_ctx, frozen_clock):
    audit = judge("fail", "fail", "pass")
    fake = FakeClova(submit("가"), submit("나"), submit("다"))
    proposal = runner.run(spec(audit, budget=Budget(max_steps=1, max_rejections=2, max_seconds=40)), {"id": "6"}, make_ctx(fake))
    assert proposal.audit["passed"] is True
    assert all(r["toolChoice"] != "auto" for r in fake.requests)  # 단계마다 마지막 단계라 제출을 강제


def test_audit_time_is_not_counted_in_deadline(make_ctx, monkeypatch):
    now = [0.0]
    monkeypatch.setattr(runner, "clock", lambda: now[0])

    def slow(args, evidence, task, ctx):
        now[0] += 100  # 감사에 100초 (담당 예산 40초보다 길다)
        return AuditVerdict("fail" if args["text"] == "가" else "pass", reason="지적", detail={})

    fake = FakeClova(submit("가"), submit("나"))
    proposal = runner.run(spec(slow), {"id": "7"}, make_ctx(fake))
    assert proposal.content == {"text": "나"} and proposal.audit["passed"] is True
    assert proposal.audit["trail"][0]["ms"] == 100000


def test_slow_audit_round_is_unchecked(make_ctx, frozen_clock):
    import time

    def stuck(args, evidence, task, ctx):
        time.sleep(0.5)
        return AuditVerdict("pass")

    proposal = runner.run(spec(stuck, audit_seconds=0.05), {"id": "8"}, make_ctx(FakeClova(submit("가"))))
    assert proposal.audit["passed"] is None and proposal.audit["trail"][0]["criterion"] == "timeout"


def test_restored_proposal_keeps_audit(tmp_path, monkeypatch, make_ctx, frozen_clock):
    monkeypatch.setattr(cache, "CACHE_PATH", tmp_path / "cache.db")
    proposal = runner.run(spec(judge("fail", "pass")), {"id": "9"}, make_ctx(FakeClova(submit("가"), submit("나"))))
    cache.clear()  # 메모리를 비우고 파일에서 되살린다
    again = runner.run(spec(judge()), {"id": "9"}, make_ctx(FakeClova()))
    assert dataclasses.asdict(again) == dataclasses.asdict(proposal) and again.audit["rounds"] == 1


def test_audit_rounds_are_traced(make_ctx, frozen_clock):
    proposal = runner.run(spec(judge("fail", "pass")), {"id": "10"}, make_ctx(FakeClova(submit("가"), submit("나"))))
    kinds = [(s["kind"], s["name"]) for s in trace.steps_of(proposal.run_id) if s["kind"] == "audit"]
    assert kinds == [("audit", "fail"), ("audit", "pass")]
