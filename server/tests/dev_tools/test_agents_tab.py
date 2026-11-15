"""개발자 대시보드 '에이전트' 탭 API와 하네스 스위치."""

import datetime as dt
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import create_app
from Harness import app_bridge, trace
from Harness.spec import Proposal


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(trace, "TRACE_PATH", tmp_path / "harness_trace.db")
    monkeypatch.setattr(settings, "agent_harness_enabled", False)
    app_bridge.forget_all()
    yield
    app_bridge.forget_all()


def test_agents_tab_shows_runs_from_both_servers():
    trace.record(run_id="a1", parent_run_id=None, agent="reply_agent", store_id="s001", step=0, kind="start", name="REVISIT_REPLY:r1")
    trace.record(run_id="a1", parent_run_id=None, agent="reply_agent", store_id="s001", step=1, kind="end", name="accepted")
    trace.record(run_id="v1", parent_run_id=None, agent="voice_reply", store_id="s001", step=0, kind="start", name="AUTO:rv_1001")
    trace.record(run_id="c1", parent_run_id="sup", agent="campaign_agent", store_id="s001", step=0, kind="start", name="POSTER:e1")
    client = TestClient(create_app())

    body = client.get("/api/dev_tools/agents").json()
    assert body["enabled"] is False
    recent = {r["run_id"]: r for r in body["recent"]}
    assert recent["a1"]["outcome"] == "accepted" and recent["a1"]["server"] == "기존 서버" and recent["a1"]["agent_name"] == "리뷰 응대"
    assert recent["v1"]["server"] == "음성 백엔드"
    assert {r["run_id"] for r in body["running"]} == {"v1", "c1"}  # 끝난 줄이 없는 실행 (일꾼 실행도 '지금 도는'에는 보인다)
    assert "c1" not in recent  # supervisor 아래 일꾼 실행은 단계 보기에서 함께 보인다
    stats = {s["agent"]: s for s in body["stats"]}
    assert stats["reply_agent"]["accepted"] == 1 and stats["voice_reply"]["running"] == 1

    steps = client.get("/api/dev_tools/agents/run", params={"run_id": "a1"}).json()["steps"]
    assert [s["kind"] for s in steps] == ["start", "end"]


def test_mode_switch_changes_setting_and_system_switches(monkeypatch):
    from app.data_pipeline import store_snapshot_cache

    cleared = []
    monkeypatch.setattr(store_snapshot_cache, "clear_snapshots", lambda: cleared.append(True))
    client = TestClient(create_app())
    assert client.post("/api/dev_tools/agents/mode", json={"enabled": True}).json() == {"AGENT_HARNESS_ENABLED": True}
    assert settings.agent_harness_enabled is True and cleared == [True]
    assert client.get("/api/dev_tools/system").json()["switches"]["AGENT_HARNESS_ENABLED"] is True
    assert client.get("/api/dev_tools/agents").json()["enabled"] is True
    client.post("/api/dev_tools/agents/mode", json={"enabled": False})
    assert settings.agent_harness_enabled is False


def test_poster_suggest_uses_agent_ments_only_when_harness_is_on(monkeypatch):
    from app.modules.poster_ai import router as poster_router
    from app.poster_ai import ment

    situation = SimpleNamespace(date=dt.date(2026, 11, 21), kind="EVENT", title="축제", lines=lambda: [], weather_tags=[])
    monkeypatch.setattr(poster_router, "_situation", lambda store_id, plan_id: situation)
    monkeypatch.setattr(ment, "suggest", lambda s: ([ment.Ment("MENU", "대표 메뉴", "기존 문구", "기존 한 줄")], "CLOVA"))
    ments = [{"kind": "EVENT", "label": "축제 손님", "headline": "축제 가는 길에", "line": "든든하게 드시고 가세요", "menu": "곱창전골"}]
    app_bridge._proposals["s001"] = {"POSTER:e1:2026-11-21": Proposal("campaign_agent", "POSTER:e1:2026-11-21", {"ments": ments}, "AGENT", "r")}
    client = TestClient(create_app())
    params = {"plan_id": "POSTER:e1:2026-11-21", "store_id": "s001"}

    off = client.get("/api/poster_ai/suggest", params=params).json()
    assert off["ment_source"] == "CLOVA" and off["ments"][0]["headline"] == "기존 문구"
    monkeypatch.setattr(settings, "agent_harness_enabled", True)
    on = client.get("/api/poster_ai/suggest", params=params).json()
    assert on["ment_source"] == "AGENT" and on["ments"][0]["headline"] == "축제 가는 길에"
