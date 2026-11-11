"""DB → 분석 → 계획 엔진 → 화면용 API 가 이어지는지 확인한다. server/ 폴더에서 `python -m pytest` 로 실행한다.

CLOVA 키를 비워서 돌린다 (문장 다듬기, 답글 초안 모두 밖으로 요청을 보내지 않는다).
"""

import datetime as dt

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.seoul_time import SEOUL
from app.data_pipeline import store_snapshot_cache
from app.main import app

NOW = dt.datetime(2026, 11, 12, 15, 0, tzinfo=SEOUL)


@pytest.fixture(autouse=True, scope="module")
def no_polish_and_fresh_cache():
    """이 파일의 테스트끼리는 계산 결과를 같이 쓴다 (가게 하나 계산에 몇 초가 걸려서)."""
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(settings, "sentence_polish_enabled", False)
        patch.setattr(settings, "clova_studio_api_key", "")
        store_snapshot_cache.clear_all()
        yield
        store_snapshot_cache.clear_all()


def test_snapshot_runs_analysis_and_planner():
    snapshot = store_snapshot_cache.get_snapshot("s001", NOW)
    assert snapshot.sales_daily and snapshot.calendar_cells and snapshot.reviews
    assert all(review.label is not None for review in snapshot.reviews)
    assert {cell.daypart for cell in snapshot.calendar_cells} == {"LUNCH", "DINNER", "NIGHT"}
    assert snapshot.plan is not None
    assert any(item.task_type == "REVISIT_REPLY" for item in snapshot.plan.plan_items)


def test_only_this_reply_week_replies_remain():
    snapshot = store_snapshot_cache.get_snapshot("s001", NOW)  # 11/12(목) → 한 주 시작 11/07(토) 11:00
    week_start = dt.datetime(2026, 11, 7, 11, 0, tzinfo=SEOUL)
    replies = [item for item in snapshot.plan.plan_items if item.task_type == "REVISIT_REPLY"]
    reviews = {review.review_id: review for review in snapshot.reviews}
    assert replies, "이번 주에 달린 리뷰 답글이 있어야 한다"
    assert len(replies) < 30  # 1년치(330개)가 아니라 이번 한 주 몫
    assert all(reviews[item.basis.ref_id].written_at >= week_start for item in replies)
    batch_ids = {entry.plan_id for batch in snapshot.plan.batches for entry in batch.entries if entry.plan_id}
    assert batch_ids <= {item.plan_id for item in snapshot.plan.plan_items}  # 알림 묶음도 남은 할 일만 가리킨다


def test_overnight_store_has_analysis_but_no_plan():
    snapshot = store_snapshot_cache.get_snapshot("s002", NOW)
    assert snapshot.calendar_cells
    assert snapshot.plan is None
    assert snapshot.plan_unavailable.code == "OVERNIGHT_STORE_NOT_SUPPORTED"


def test_snapshot_is_reused_until_refresh_time():
    first = store_snapshot_cache.get_snapshot("s001", NOW)
    assert store_snapshot_cache.get_snapshot("s001", NOW + dt.timedelta(minutes=5)) is first
    assert store_snapshot_cache.get_snapshot("s001", NOW + dt.timedelta(minutes=30)) is not first


ENDPOINTS = [
    "/api/today",
    "/api/plan?from=2026-11-01&to=2026-11-30",
    "/api/calendar",
    "/api/reviews?quick=true",
    "/api/settings",
    "/api/sales?grain=weekday_daypart",
    "/api/sales/live",
    "/api/sales/weeks",
    "/api/sales/menus?period=4w",
    "/api/sales/times?period=month",
    "/api/sales/channels?period=week",
    "/api/sales/months",
    "/api/staff",
    "/api/staff/shifts",
    "/api/naver/place",
    "/api/calendar?store_id=s003",
]


@pytest.mark.parametrize("path", ENDPOINTS)
def test_screen_api_returns_real_data(path):
    response = TestClient(app).get(path)
    assert response.status_code == 200, response.text
    assert response.json()["is_example"] is False


def test_unknown_store_is_404():
    response = TestClient(app).get("/api/today?store_id=s999")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "STORE_NOT_FOUND"


def test_settings_patch_changes_slots_and_rejects_busy_time():
    client = TestClient(app)
    ok = client.patch("/api/settings?store_id=s003", json={"slots": {"OPENING": "10:30", "AFTERNOON": "15:00", "CLOSING": "20:30"}})
    assert ok.status_code == 200
    assert ok.json()["settings"]["slots"]["AFTERNOON"] == "15:00"
    busy = client.patch("/api/settings?store_id=s003", json={"slots": {"OPENING": "10:30", "AFTERNOON": "12:00", "CLOSING": "20:30"}})
    assert busy.status_code == 400
    assert busy.json()["error"]["code"] == "SLOT_IN_BUSY_DAYPART"


def test_plan_items_have_draft_text_field():
    items = TestClient(app).get("/api/plan?from=2026-11-01&to=2026-11-30").json()["plan_items"]
    assert items and all("draft_text" in item for item in items)  # 키가 없으면 값은 None


def test_rewrite_without_clova_key_is_503():
    response = TestClient(app).post("/api/replies/rewrite", json={"text": "감사합니다. 또 오세요.", "style": "short"})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "CLOVA_NOT_CONFIGURED"


def test_sales_menus_uses_from_as_field_name():
    body = TestClient(app).get("/api/sales/menus?period=week").json()
    assert "from" in body and "from_" not in body
