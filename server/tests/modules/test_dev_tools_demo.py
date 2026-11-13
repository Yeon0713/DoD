"""개발자 대시보드 시연 탭 테스트: Figma UC01~UC16 단계 만들기와 서버 시계 옮기기. 진짜 CLOVA 는 부르지 않는다."""

import datetime as dt
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.seoul_time import SEOUL, clock_shift, now_seoul, set_clock_shift
from app.data_pipeline import store_snapshot_cache
from app.main import create_app
from app.modules.dev_tools import demo_scenario, demo_week_scan


@pytest.fixture
def short_demo(monkeypatch):
    """시연 기간을 월·화 이틀로 줄여 빨리 훑는다 (s001 은 월 밤과 화 오후에 불만 리뷰 답글이 온다)."""
    monkeypatch.setattr(demo_week_scan, "DEMO_DAYS", 2)
    monkeypatch.setattr(demo_scenario, "DEMO_DAYS", 2)
    demo_week_scan.forget()
    yield
    demo_week_scan.forget()


def test_steps_follow_uc_order_and_open_the_complaint_reply(short_demo):
    result = demo_scenario.build_steps("s001")
    ucs = [step["uc"] for step in result["steps"]]
    assert ucs == sorted(ucs)  # UC01 → UC16 순서
    assert set(ucs) == set(demo_scenario.UC_TITLES)  # UC 16개가 모두 있다

    home = next(step for step in result["steps"] if step["figma"] == "09-h1")
    assert home["available"]
    assert home["at"] == "2026-11-09T21:35:00+09:00"  # 월요일 마감 전 알림 5분 뒤
    assert home["open"]["card"] == "APPROVAL_REQUEST:REVISIT_REPLY:rv_329:2026-11-09"

    reply = next(step for step in result["steps"] if step["figma"] == "09-5")
    assert reply["open"]["to"] == "/reply/REVISIT_REPLY%3Arv_329%3A2026-11-09"


def test_steps_without_data_are_greyed_with_reason(short_demo):
    result = demo_scenario.build_steps("s002")  # 자정을 넘겨 여는 가게: 계획이 없다
    assert result["unavailable"]
    reply = next(step for step in result["steps"] if step["figma"] == "09-h1")
    assert not reply["available"] and "계획을 못 만들었어요" in reply["reason"]
    settings_step = next(step for step in result["steps"] if step["figma"] == "09-19")
    assert settings_step["available"]  # 가게와 상관없는 화면은 열린다


def test_demo_go_needs_dev_clock(monkeypatch):
    monkeypatch.setattr(settings, "dev_tools_enabled", True)
    monkeypatch.setattr(settings, "dev_clock_enabled", False)
    client = TestClient(create_app())
    response = client.post("/api/dev_tools/demo_go", json={"store_id": "s001", "at": "2026-11-09T21:35:00+09:00"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "DEV_CLOCK_OFF"


def test_demo_go_moves_server_clock_and_reset_brings_it_back(monkeypatch):
    monkeypatch.setattr(settings, "dev_tools_enabled", True)
    monkeypatch.setattr(settings, "dev_clock_enabled", True)
    forgotten = []
    monkeypatch.setattr(store_snapshot_cache, "forget", forgotten.append)
    asked = {}

    def fake_snapshot(store_id, **options):
        asked.update(options)
        return SimpleNamespace(computed_at=now_seoul())

    monkeypatch.setattr(store_snapshot_cache, "get_snapshot", fake_snapshot)
    client = TestClient(create_app())
    try:
        response = client.post("/api/dev_tools/demo_go", json={"store_id": "s001", "at": "2026-11-09T21:35:00+09:00"})
        assert response.status_code == 200
        target = dt.datetime(2026, 11, 9, 21, 35, tzinfo=SEOUL)
        assert abs((now_seoul() - target).total_seconds()) < 5
        assert forgotten == ["s001"]  # 앞 결과 없이 다시 계산해야 늘 같은 화면이 나온다
        assert asked == {"wait_for_drafts": False, "polish": False}  # CLOVA 를 기다리지 않고, 문장 다듬기는 기본으로 끈다

        assert client.post("/api/dev_tools/demo_clock_reset").status_code == 200
        assert clock_shift() == dt.timedelta(0)
    finally:
        set_clock_shift(dt.timedelta(0))
