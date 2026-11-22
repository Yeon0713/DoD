"""기존 서버 흐름 연결(app_bridge)과 실행 기록 요약(trace.recent_runs)."""

import datetime as dt
from types import SimpleNamespace

import pytest

from app.core.config import settings
from app.menu_board.menu_candidates import EMPTY
from Harness import app_bridge, runner, supervisor, trace
from Harness.agents import campaign_agent, complaint_agent, reply_agent
from Harness.spec import AgentSpec, Proposal, Tool
from Harness.tests.fakes import FakeClova, call
from Harness.tools import obj, string

R1, R4, NUDGE = "REVISIT_REPLY:r1:2026-11-15", "REVISIT_REPLY:r4:2026-11-15", "REORDER_NUDGE:c1:2026-11-15"
MENU, POSTER = "MENU_ORDER:2026-11-21:2026-11-21", "POSTER:e1:2026-11-21"


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    app_bridge.forget_all()
    monkeypatch.setattr(settings, "agent_harness_enabled", False)
    yield
    app_bridge.forget_all()


def fake_agents(monkeypatch, seen: list[str]):
    def reply(item, ctx, **kwargs):
        seen.append(item.plan_id)
        return Proposal("reply_agent", item.plan_id, {"kind": "REPLY", "text": f"에이전트 답글 {item.plan_id}"}, "AGENT", ctx.run_id)

    def complaint(item, ctx, **kwargs):
        seen.append(item.plan_id)
        return Proposal("complaint_agent", item.plan_id, {"hypotheses": [{"text": "저녁 7시 주문 몰림", "evidence": "x"}]}, "AGENT", ctx.run_id)

    def campaign(item, ctx, **kwargs):
        seen.append(item.plan_id)
        ments = [{"kind": "EVENT", "label": "축제 손님", "headline": "축제 가는 길에", "line": "든든하게 드시고 가세요", "menu": "비빔국수"}]
        return Proposal("campaign_agent", item.plan_id, {"theme": "축제", "menu_ids": ["m2", "m3"], "reason": "축제 날 많이 팔림",
                                                          "ments": ments if item.task_type == "POSTER" else []}, "AGENT", ctx.run_id)

    monkeypatch.setattr(reply_agent, "draft", reply)
    monkeypatch.setattr(complaint_agent, "diagnose", complaint)
    monkeypatch.setattr(campaign_agent, "plan_campaign", campaign)
    monkeypatch.setattr(supervisor, "coordinate_batch", lambda batch, proposals, ctx: SimpleNamespace(source="NONE"))


def test_switch_off_does_nothing(snapshot):
    assert app_bridge.start(snapshot, [R1]) is False
    assert app_bridge.known_drafts("t001", [R1]) == {}
    assert app_bridge.menu_lookup({"store_id": "t001"}, [], "LOCAL_FESTIVAL") is EMPTY


def test_run_all_fills_drafts_menu_candidates_and_poster_ments(snapshot, monkeypatch):
    seen: list[str] = []
    fake_agents(monkeypatch, seen)
    app_bridge.run_all(snapshot, [R1, R4, NUDGE])
    assert set(seen) >= {R1, R4, NUDGE, MENU, POSTER} and any(pid.startswith("REVIEW_FIX:") for pid in seen)
    assert snapshot.draft_texts[R1] == f"에이전트 답글 {R1}"  # 앱이 보는 초안 자리를 채운다
    assert app_bridge.known_drafts("t001", [R1, "없음"]) == {R1: f"에이전트 답글 {R1}"}
    candidates = app_bridge.menu_lookup({"store_id": "t001"}, [], "LOCAL_FESTIVAL")
    assert candidates.menu_ids == ("m2", "m3") and candidates.reason == "축제 날 많이 팔림"
    assert app_bridge.poster_ments("t001", POSTER)[0]["headline"] == "축제 가는 길에"
    assert app_bridge.poster_ments("t001", MENU) is None
    status = app_bridge.status()["stores"][0]
    assert status["job"]["state"] == "done" and status["job"]["done"] == status["job"]["total"]
    assert {p["agent"] for p in status["proposals"]} == {"reply_agent", "complaint_agent", "campaign_agent"}

    # 다시 계산해도 이미 제안이 있는 할 일은 다시 돌리지 않는다
    seen.clear()
    app_bridge.run_all(snapshot, [R1, R4, NUDGE])
    assert seen == []


def test_supervisor_revision_replaces_the_draft(snapshot, monkeypatch):
    from app.planner.data_shapes import BatchEntry, NotificationBatch

    fake_agents(monkeypatch, [])
    batch = NotificationBatch(slot_at=snapshot.computed_at + dt.timedelta(hours=3), slot="AFTERNOON",
                              entries=[BatchEntry(plan_id=R1, notify_kind="APPROVAL_REQUEST", priority=2)])
    far = NotificationBatch(slot_at=snapshot.computed_at + dt.timedelta(days=3), slot="AFTERNOON",
                            entries=[BatchEntry(plan_id=R4, notify_kind="APPROVAL_REQUEST", priority=2)])
    snapshot.plan = snapshot.plan.model_copy(update={"batches": [batch, far]})
    revised = Proposal("reply_agent", R1, {"kind": "REPLY", "text": "조율된 답글"}, "AGENT", "child")
    seen_batches = []

    def coordinate(batch, proposals, ctx):
        seen_batches.append(batch.slot_at)
        return SimpleNamespace(source="AGENT", proposals={**proposals, R1: revised}, run_id=ctx.run_id,
                               headline="오늘은 맛 불만 정리가 먼저예요", conflicts=[], item_notes={})

    monkeypatch.setattr(supervisor, "coordinate_batch", coordinate)
    app_bridge.run_all(snapshot, [R1, R4])
    assert seen_batches == [batch.slot_at]  # 24시간 안 묶음만 조율한다
    assert snapshot.draft_texts[R1] == "조율된 답글"
    assert app_bridge.status()["stores"][0]["batches"][0]["headline"] == "오늘은 맛 불만 정리가 먼저예요"


def test_bad_supervisor_result_does_not_stop_other_batches(snapshot, monkeypatch):
    """묶음 하나의 결과가 이상해도(제안 자리에 dict) 남은 묶음과 작업 상태는 끝까지 간다 (H1 방어)."""
    from app.planner.data_shapes import BatchEntry, NotificationBatch

    fake_agents(monkeypatch, [])
    bad = NotificationBatch(slot_at=snapshot.computed_at + dt.timedelta(hours=1), slot="AFTERNOON",
                            entries=[BatchEntry(plan_id=R1, notify_kind="APPROVAL_REQUEST", priority=2)])
    good = NotificationBatch(slot_at=snapshot.computed_at + dt.timedelta(hours=3), slot="AFTERNOON",
                             entries=[BatchEntry(plan_id=R4, notify_kind="APPROVAL_REQUEST", priority=2)])
    snapshot.plan = snapshot.plan.model_copy(update={"batches": [bad, good]})

    def coordinate(batch, proposals, ctx):
        broken = {R1: {"agent": "reply_agent", "content": {"text": "dict"}}} if batch is bad else {}
        return SimpleNamespace(source="AGENT", proposals={**proposals, **broken}, run_id=ctx.run_id,
                               headline="묶음 첫 줄이에요", conflicts=[], item_notes={})

    monkeypatch.setattr(supervisor, "coordinate_batch", coordinate)
    app_bridge.run_all(snapshot, [R1, R4])
    store = app_bridge.status()["stores"][0]
    assert store["job"]["state"] == "done"
    assert [b["slot_at"] for b in store["batches"]] == [good.slot_at.isoformat(timespec="minutes")]


def test_bad_agent_result_does_not_stop_other_items(snapshot, monkeypatch):
    """할 일 하나의 결과가 이상해도(제안 자리에 dict) 남은 할 일과 supervisor 조율은 끝까지 간다 (H9)."""
    from app.planner.data_shapes import BatchEntry, NotificationBatch

    fake_agents(monkeypatch, [])
    called: list[str] = []

    def reply(item, ctx, **kwargs):
        called.append(item.plan_id)
        if len(called) == 1:  # 첫 할 일만 모양이 틀린 값
            return {"agent": "reply_agent", "content": {"text": "dict"}}
        return Proposal("reply_agent", item.plan_id, {"kind": "REPLY", "text": f"에이전트 답글 {item.plan_id}"}, "AGENT", ctx.run_id)

    monkeypatch.setattr(reply_agent, "draft", reply)
    batch = NotificationBatch(slot_at=snapshot.computed_at + dt.timedelta(hours=1), slot="AFTERNOON",
                              entries=[BatchEntry(plan_id=R4, notify_kind="APPROVAL_REQUEST", priority=2)])
    snapshot.plan = snapshot.plan.model_copy(update={"batches": [batch]})
    monkeypatch.setattr(supervisor, "coordinate_batch", lambda batch, proposals, ctx: SimpleNamespace(
        source="AGENT", proposals=proposals, run_id=ctx.run_id, headline="묶음 첫 줄이에요", conflicts=[], item_notes={}))

    app_bridge.run_all(snapshot, [R1, R4, NUDGE])
    assert len(called) == 3
    proposals = app_bridge._proposals["t001"]
    assert called[0] not in proposals and all(pid in proposals for pid in called[1:])
    assert MENU in proposals and POSTER in proposals  # 뒤쪽 할 일도 돌았다
    store = app_bridge.status()["stores"][0]
    assert store["job"]["state"] == "done"
    assert [b["slot_at"] for b in store["batches"]] == [batch.slot_at.isoformat(timespec="minutes")]  # supervisor 가 불렸다


def test_set_enabled_clears_results_and_snapshots(snapshot, monkeypatch):
    from app.data_pipeline import store_snapshot_cache

    fake_agents(monkeypatch, [])
    app_bridge.run_all(snapshot, [R1])
    cleared = []
    monkeypatch.setattr(store_snapshot_cache, "clear_snapshots", lambda: cleared.append(True))
    assert app_bridge.set_enabled(True) == {"AGENT_HARNESS_ENABLED": True}
    assert settings.agent_harness_enabled is True and cleared == [True]
    assert app_bridge.known_drafts("t001", [R1]) == {}


def test_start_queues_once_per_store(snapshot, monkeypatch):
    monkeypatch.setattr(settings, "agent_harness_enabled", True)
    submitted = []
    monkeypatch.setattr(app_bridge._executor, "submit", lambda fn, *args: submitted.append(args))
    assert app_bridge.start(snapshot, [R1]) is True
    assert app_bridge.start(snapshot, [R1]) is False  # 같은 가게 작업이 기다리는 중이면 또 맡기지 않는다
    assert len(submitted) == 1 and app_bridge.status()["stores"][0]["job"]["state"] == "queued"


def test_snapshot_uses_agents_instead_of_single_call_when_on(monkeypatch):
    """스위치를 켜면 가게 계산이 기존 write_drafts 를 부르지 않고 에이전트 작업을 맡긴다. 끄면 그 반대."""
    from app.data_pipeline import store_snapshot_cache

    started, single = [], []
    monkeypatch.setattr(store_snapshot_cache, "write_drafts", lambda *args: single.append(True) or {})
    monkeypatch.setattr(app_bridge._executor, "submit", lambda fn, *args: started.append(args))
    now = dt.datetime(2026, 11, 14, 15, 0, tzinfo=dt.timezone(dt.timedelta(hours=9)))

    monkeypatch.setattr(settings, "agent_harness_enabled", True)
    store_snapshot_cache._compute("s001", now, None, polish=False)
    assert started and not single

    started.clear()
    app_bridge.forget_all()
    monkeypatch.setattr(settings, "agent_harness_enabled", False)
    store_snapshot_cache._compute("s001", now, None, polish=False)
    assert single and not started


# ── 실행 기록 요약 ──


def tiny_spec(name="tiny") -> AgentSpec:
    return AgentSpec(
        name=name, system_prompt=lambda t, c: "s", user_message=lambda t, c: f"u{t['id']}", tools=[],
        submit=Tool("submit_text", "제출", obj({"text": string("글")})),
        check=lambda args, ev, t, c, notes: None if args.get("text") == "좋아" else "다시",
        task_id=lambda t: t["id"], fallback=lambda t, c: {"text": "기본"},
    )


def test_recent_runs_summarizes_outcomes(make_ctx, frozen_clock):
    runner.run(tiny_spec(), {"id": "A"}, make_ctx(FakeClova([call("submit_text", {"text": "좋아"})])))
    runner.run(tiny_spec(), {"id": "B"}, make_ctx(FakeClova([call("submit_text", {"text": "별로"})], [call("submit_text", {"text": "별로"})])))
    runner.run(tiny_spec(), {"id": "A"}, make_ctx(FakeClova()))  # 캐시
    trace.record(run_id="live", parent_run_id=None, agent="voice_reply", store_id="s001", step=0, kind="start", name="AUTO:rv_1")
    runs = {r["task"]: r for r in trace.recent_runs()}
    assert runs["B"]["outcome"] == "fallback" and runs["B"]["rejections"] == 2 and runs["B"]["llm_calls"] == 2
    assert runs["AUTO:rv_1"]["outcome"] == "running" and runs["AUTO:rv_1"]["agent"] == "voice_reply"
    outcomes = sorted(r["outcome"] for r in trace.recent_runs() if r["task"] == "A")
    assert outcomes == ["accepted", "cache"]


def test_quiet_unfinished_run_is_stalled():
    trace.record(run_id="old", parent_run_id=None, agent="reply_agent", store_id="t001", step=0, kind="start", name="X")
    an_hour_ago = (trace.now_seoul() - dt.timedelta(hours=1)).isoformat(timespec="seconds")
    with trace._db() as conn:  # 서버가 꺼져 끝난 줄을 못 남긴 실행처럼 만든다
        conn.execute("UPDATE steps SET at = ? WHERE run_id = 'old'", (an_hour_ago,))
    run = next(r for r in trace.recent_runs() if r["run_id"] == "old")
    assert run["outcome"] == "stalled"


def test_fallback_poster_ments_are_not_reported_as_agent(snapshot, monkeypatch):
    fake_agents(monkeypatch, [])
    monkeypatch.setattr(campaign_agent, "plan_campaign", lambda item, ctx, **kw: Proposal(
        "campaign_agent", item.plan_id, {"menu_ids": [], "ments": [{"kind": "MENU", "label": "기본", "headline": "기본", "line": "기본"}]},
        "FALLBACK", ctx.run_id))
    app_bridge.run_all(snapshot, [])
    assert app_bridge.poster_ments("t001", POSTER) is None  # 부르는 쪽이 기존 ment.suggest 를 쓰고 출처도 그대로 보인다
