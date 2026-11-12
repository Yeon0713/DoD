"""개발자 대시보드 "화면 글" 탭 API(/api/dev_tools/ui_text) 테스트.

저장(save)과 코드에 넣기(apply)는 진짜 파일을 바꾸므로 Node 스크립트를 부르지 않고 가짜 실행으로 확인한다.
글 읽기(data)는 파일을 바꾸지 않아서 node 와 mobile/node_modules 가 있으면 진짜로 불러 본다.
"""

import json
import shutil
import subprocess

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import create_app
from app.modules.dev_tools import ui_text

EDIT = {"file": "src/components/start/StartScreens.tsx", "line": 10, "func": "IntroScreen", "original": "원본", "edited": "수정본"}


@pytest.fixture
def dashboard(monkeypatch):
    monkeypatch.setattr(settings, "dev_tools_enabled", True)
    return TestClient(create_app())


@pytest.fixture
def fake_node(monkeypatch):
    """subprocess.run 을 가로채 부른 명령과 넘긴 글을 기록하고, 정해 둔 답을 돌려준다."""
    calls = []
    answer = {"stdout": "{}", "stderr": "", "returncode": 0}

    def run(args, **kwargs):
        calls.append({"command": args[-1], "input": json.loads(kwargs["input"])})
        return subprocess.CompletedProcess(args, answer["returncode"], answer["stdout"], answer["stderr"])

    monkeypatch.setattr(ui_text.shutil, "which", lambda name: "/usr/bin/node")
    monkeypatch.setattr(ui_text.subprocess, "run", run)
    return calls, answer


def test_ui_text_is_closed_when_dashboard_off(monkeypatch):
    monkeypatch.setattr(settings, "dev_tools_enabled", False)
    client = TestClient(create_app())
    assert client.get("/api/dev_tools/ui_text").status_code == 404
    assert client.post("/api/dev_tools/ui_text/save", json={"edits": {}}).status_code == 404


def test_save_passes_edits_to_script(dashboard, fake_node):
    calls, answer = fake_node
    answer["stdout"] = json.dumps({"ok": True, "count": 1, "at": "2026-11-13T00:00:00Z"})
    res = dashboard.post("/api/dev_tools/ui_text/save", json={"edits": {"a::b::c::0": EDIT}})
    assert res.status_code == 200 and res.json()["count"] == 1
    assert calls == [{"command": "save", "input": {"edits": {"a::b::c::0": EDIT}}}]


def test_apply_returns_script_result(dashboard, fake_node):
    calls, answer = fake_node
    answer["stdout"] = json.dumps({"applied": [{"file": EDIT["file"]}], "failed": [], "check": {"ok": True, "output": ""}})
    res = dashboard.post("/api/dev_tools/ui_text/apply", json={"edits": {"a::b::c::0": EDIT}})
    assert res.status_code == 200 and res.json()["check"]["ok"] is True
    assert calls[0]["command"] == "apply"


def test_bad_edit_is_refused_before_script(dashboard, fake_node):
    calls, _ = fake_node
    res = dashboard.post("/api/dev_tools/ui_text/save", json={"edits": {"x": {"original": "원본"}}})
    assert res.status_code == 422 and calls == []


def test_script_failure_shows_last_lines_without_cert_noise(dashboard, fake_node):
    _, answer = fake_node
    answer.update(returncode=1, stdout="", stderr="ERROR: failed to copy trust settings of system certificate\nError: 깨졌어요")
    res = dashboard.get("/api/dev_tools/ui_text")
    assert res.status_code == 500
    message = res.json()["error"]["message"]
    assert "깨졌어요" in message and "trust settings" not in message


def test_missing_node_is_explained(dashboard, monkeypatch):
    monkeypatch.setattr(ui_text.shutil, "which", lambda name: None)
    res = dashboard.get("/api/dev_tools/ui_text")
    assert res.status_code == 503 and "node" in res.json()["error"]["message"]


@pytest.mark.skipif(
    shutil.which("node") is None or not (ui_text.MOBILE / "node_modules" / "typescript").is_dir(),
    reason="node 또는 mobile/node_modules 가 없어요",
)
def test_real_data_lists_screens(dashboard):
    body = dashboard.get("/api/dev_tools/ui_text").json()
    routes = {g.get("route") for g in body["groups"]}
    assert "/start" in routes and body["total"] > 0
    assert body["editsFile"] == "mobile/scripts/ui-text/edits.json"
