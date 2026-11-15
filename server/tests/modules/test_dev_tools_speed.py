"""개발자 대시보드 빠르게 하기 테스트 (docs/dev-dashboard-optimization.md).

- 시연 훑기: DB 를 한 번만 읽고 시각마다 걸러 써도 결과가 같다
- 훑은 결과를 파일에 남겨 서버를 다시 켜도 다시 쓰고, 데이터나 설정이 바뀌면 다시 훑는다
- 시연 단계를 열 때 CLOVA 답글 초안을 기다리지 않는다
- 분석·알림 타임라인 탭은 보관해 둔 결과를 보여 준다
진짜 CLOVA 는 부르지 않는다.
"""

import datetime as dt

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.seoul_time import at_time
from app.data_pipeline import store_snapshot_cache
from app.data_pipeline.db_rows_to_analysis_inputs import build_analysis_inputs, inputs_until
from app.main import create_app
from app.modules.dev_tools import data_provider, demo_scenario, demo_week_scan

MOMENTS = [at_time(dt.date(2026, 11, 9), "11:05"), at_time(dt.date(2026, 11, 10), "15:05"), at_time(dt.date(2026, 11, 10), "21:35")]


@pytest.fixture
def short_demo(monkeypatch):
    monkeypatch.setattr(demo_week_scan, "DEMO_DAYS", 2)
    monkeypatch.setattr(demo_scenario, "DEMO_DAYS", 2)
    demo_week_scan.forget()
    yield
    demo_week_scan.forget()


@pytest.mark.parametrize("store_id", ["s001", "s003"])
def test_inputs_until_matches_reading_db_at_each_time(store_id):
    full = build_analysis_inputs(store_id, max(MOMENTS))
    for moment in MOMENTS:
        assert inputs_until(full, moment) == build_analysis_inputs(store_id, moment)


def test_plan_at_times_matches_plan_only():
    steps = []
    many = store_snapshot_cache.plan_at_times("s001", MOMENTS, on_step=steps.append)
    assert steps == [1, 2, 3]
    for moment, (settings_many, plan_many, _) in zip(MOMENTS, many):
        settings_one, plan_one, _ = store_snapshot_cache.plan_only("s001", moment)
        assert settings_many == settings_one
        assert plan_many == plan_one


def test_scan_is_saved_and_reused_after_restart(short_demo, monkeypatch):
    first = demo_week_scan.scan_week("s001")
    assert (demo_week_scan.SAVE_DIR / "s001.json").exists()
    assert demo_week_scan.is_ready("s001")

    demo_week_scan._scans.clear()  # 서버를 다시 켠 것처럼 메모리를 비운다
    monkeypatch.setattr(demo_week_scan, "_scan", lambda store_id: pytest.fail("파일이 있으면 다시 훑지 않아야 한다"))
    assert demo_week_scan.scan_week("s001") == first


def test_scan_is_redone_when_owner_settings_change(short_demo, monkeypatch):
    demo_week_scan.scan_week("s001")
    redone = []
    monkeypatch.setattr(demo_week_scan, "_scan", lambda store_id: redone.append(store_id) or demo_week_scan.WeekScan(store_id))
    monkeypatch.setattr(store_snapshot_cache, "get_settings_changes", lambda store_id: {"work_hours": "바뀜"})
    demo_week_scan.scan_week("s001")
    assert redone == ["s001"]


def test_forget_removes_saved_file(short_demo):
    demo_week_scan.scan_week("s003")
    demo_week_scan.forget("s003")
    assert not (demo_week_scan.SAVE_DIR / "s003.json").exists()
    assert not demo_week_scan.is_ready("s003")


def test_demo_progress_api(short_demo, monkeypatch):
    monkeypatch.setattr(settings, "dev_tools_enabled", True)
    demo_week_scan.scan_week("s003")  # 목업 가게만 쓴다 (등록 가게는 초기화하면 사라진다)
    body = TestClient(create_app()).get("/api/dev_tools/demo_progress").json()
    assert body["ready"]["s003"] is True and body["ready"]["s001"] is False
    assert body["progress"] == {}


def test_snapshot_does_not_wait_for_drafts(monkeypatch):
    monkeypatch.setattr(store_snapshot_cache, "write_drafts", lambda *a: pytest.fail("기다리며 초안을 쓰면 안 된다"))
    later = []
    monkeypatch.setattr(store_snapshot_cache._draft_executor, "submit", lambda fn, *args: later.append(args))
    store_snapshot_cache.forget("s001")
    try:
        snapshot = store_snapshot_cache.get_snapshot("s001", MOMENTS[1], wait_for_drafts=False, polish=False)
        assert snapshot.plan is not None
        assert len(later) == 1  # 초안은 뒤에서 쓴다
    finally:
        store_snapshot_cache.forget("s001")


def test_analysis_tab_uses_kept_snapshot(monkeypatch):
    kept = object()
    monkeypatch.setattr(store_snapshot_cache, "cached_snapshot", lambda store_id: kept)
    monkeypatch.setattr(store_snapshot_cache, "get_snapshot", lambda *a, **k: pytest.fail("보관한 결과가 있으면 다시 계산하지 않는다"))
    assert data_provider._kept_snapshot("s001") is kept


def test_clova_log_clear_api_is_gone(monkeypatch):
    monkeypatch.setattr(settings, "dev_tools_enabled", True)
    assert TestClient(create_app()).post("/api/dev_tools/clova_log/clear").status_code in (404, 405)


def test_other_store_registration_keeps_this_scan(short_demo, monkeypatch):
    """다른 가게를 등록하거나 초기화로 지워도(등록 기록 파일이 바뀌어도) 이 가게 결과는 그대로 쓴다."""
    from app.data_pipeline import registered_stores

    demo_week_scan.scan_week("s001")
    real = registered_stores.place_info
    monkeypatch.setattr(registered_stores, "place_info", lambda store_id: object() if store_id == "s999" else real(store_id))
    assert demo_week_scan.is_ready("s001")
