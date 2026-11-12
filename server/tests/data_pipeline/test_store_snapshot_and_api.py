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


def test_settings_patch_drops_duplicate_busy_dayparts():
    client = TestClient(app)
    response = client.patch("/api/settings?store_id=s003", json={"busy_dayparts": ["LUNCH", "LUNCH", "DINNER"]})
    assert response.status_code == 200
    assert response.json()["settings"]["busy_dayparts"] == ["LUNCH", "DINNER"]


def _menu_order(snapshot, plan_id):
    return next(item for item in snapshot.plan.plan_items if item.plan_id == plan_id)


def test_approval_request_time_does_not_slide_when_recomputed():
    """승인 요청 시각이 지난 뒤에 다시 계산해도 그 시각이 다음 알림 시각으로 밀리지 않는다.

    밀리면 앱(오늘 도착한 알림만 보여 준다)에 승인 요청 카드가 한 번도 뜨지 않는다.
    """
    plan_id = "MENU_ORDER:2026-11-18:2026-11-18"
    asked_at = dt.datetime(2026, 11, 17, 14, 0, tzinfo=SEOUL)
    for now in (dt.datetime(2026, 11, 17, 13, 50, tzinfo=SEOUL), dt.datetime(2026, 11, 17, 14, 20, tzinfo=SEOUL)):
        snapshot = store_snapshot_cache.get_snapshot("s001", now)
        item = _menu_order(snapshot, plan_id)
        assert item.approval_request_at == asked_at
        assert item.execute_at == dt.datetime(2026, 11, 18, 10, 0, tzinfo=SEOUL)
        calendar_items = [i for i in snapshot.plan.plan_items if i.task_type in ("MENU_ORDER", "POSTER")]
        assert all(i.execute_at >= i.approval_request_at for i in calendar_items)  # 승인 요청이 실행보다 먼저


def test_menu_order_execute_reminder_remains_on_the_day():
    """메뉴판을 바꾸는 날 아침에도 그 할 일이 남아 실행 알림이 간다 (달력은 오늘부터라 전에는 사라졌다)."""
    now = dt.datetime(2026, 11, 18, 10, 5, tzinfo=SEOUL)
    snapshot = store_snapshot_cache.get_snapshot("s001", now)
    today_entries = [
        (entry.plan_id, entry.notify_kind)
        for batch in snapshot.plan.batches
        if batch.slot_at.date() == now.date()
        for entry in batch.entries
    ]
    assert ("MENU_ORDER:2026-11-18:2026-11-18", "EXECUTE_REMINDER") in today_entries
    # 어제 칸을 붙여서 생긴 지난 일은 없다
    yesterday = now.date() - dt.timedelta(days=1)
    assert all(notice.slot_at.date() != yesterday for notice in snapshot.plan.notice_items)
    assert all(item.plan_id != f"POSTER:{yesterday}:{yesterday}" for item in snapshot.plan.plan_items)
    # 화면에 보내는 달력은 그대로 오늘부터 35일이다
    assert min(cell.date for cell in snapshot.calendar_cells) == now.date()


def test_store_closed_on_monday_gets_weekly_preview_on_first_open_day():
    """월요일 휴무 가게(s003)는 주간 예고가 화요일 출근 후에 온다."""
    snapshot = store_snapshot_cache.get_snapshot("s003", NOW)
    previews = [notice for notice in snapshot.plan.notice_items if notice.kind == "WEEKLY_PREVIEW"]
    assert previews, "월요일이 휴무여도 주간 예고가 있어야 한다"
    assert all(notice.slot_at.weekday() == 1 for notice in previews)  # 화요일
    assert previews[0].notice_id == "WEEKLY_PREVIEW:2026-11-16"


def test_settings_patch_keeps_weekly_hours_and_closed_days():
    """장사 시간을 고치면 쉬는 날, 요일별 시간, 브레이크 타임이 남고 계획 엔진이 쉬는 날을 따른다."""
    client = TestClient(app)
    day = {"open": "10:00", "close": "22:00"}
    weekly = {code: day for code in ("TUE", "WED", "THU", "FRI", "SAT")} | {"MON": None, "SUN": {"open": "10:00", "close": "20:00"}}
    body = {"weekly_hours": weekly, "break_time": {"start": "15:00", "end": "16:30"}}
    try:
        saved = client.patch("/api/settings?store_id=s001", json=body)
        assert saved.status_code == 200
        settings_now = client.get("/api/settings?store_id=s001").json()["settings"]
        assert settings_now["closed_weekdays"] == ["MON"]
        assert (settings_now["open_time"], settings_now["close_time"]) == ("10:00", "22:00")  # 가장 많은 요일의 시간
        assert settings_now["weekly_hours"]["SUN"] == {"open": "10:00", "close": "20:00"}
        assert settings_now["weekly_hours"]["MON"] is None
        assert settings_now["break_time"] == {"start": "15:00", "end": "16:30"}
        # 쉬는 월요일에는 알림 묶음이 없다
        snapshot = store_snapshot_cache.get_snapshot("s001", NOW)
        assert all(batch.slot_at.weekday() != 0 for batch in snapshot.plan.batches)
        # 브레이크 타임을 null 로 보내면 없어진다
        cleared = client.patch("/api/settings?store_id=s001", json={"break_time": None})
        assert cleared.json()["settings"]["break_time"] is None
        # 일주일 내내 쉬는 날은 받지 않는다
        none_open = client.patch("/api/settings?store_id=s001", json={"weekly_hours": {code: None for code in weekly}})
        assert none_open.status_code == 400 and none_open.json()["error"]["code"] == "NO_OPEN_DAY"
    finally:
        store_snapshot_cache.clear_all()  # 다른 테스트가 고친 설정을 물려받지 않게


def test_closed_day_store_gets_nothing_on_closed_day_and_keeps_next_day_menu_order():
    """월요일 휴무 가게(s003): 월요일로 잡히는 알림이 없고, 화요일에 시작하는 변화도 메뉴판 제안이 생긴다."""
    now = dt.datetime(2026, 12, 8, 10, 35, tzinfo=SEOUL)  # 화요일. 12/9(수) 경기 포스터는 이틀 전인 월요일이 휴무다
    snapshot = store_snapshot_cache.get_snapshot("s003", now)
    plan = snapshot.plan
    assert all(batch.slot_at.weekday() != 0 for batch in plan.batches)
    times = [t for item in plan.plan_items for t in (item.approval_request_at, item.execute_at) if t is not None]
    recent = [t for t in times if abs((t.date() - now.date()).days) <= 14]
    assert recent and all(t.weekday() != 0 for t in recent)
    today_entries = {
        (entry.plan_id, entry.notify_kind)
        for batch in plan.batches
        if batch.slot_at.date() == now.date()
        for entry in batch.entries
    }
    assert ("POSTER:game_004:2026-12-09", "EXECUTE_REMINDER") in today_entries  # 월요일 대신 화요일 출근 후
    assert ("MENU_ORDER:2026-12-08:2026-12-08", "APPROVAL_REQUEST") in today_entries  # 휴무 다음 날의 메뉴판 제안
