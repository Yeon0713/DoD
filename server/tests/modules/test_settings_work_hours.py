"""출근·퇴근 시간과 더 넣은 알림 (PATCH /api/settings). 고친 값은 서버 메모리에만 있어 DB 파일은 바뀌지 않는다."""

import pytest
from fastapi.testclient import TestClient

from app.data_pipeline import store_snapshot_cache
from app.main import create_app


@pytest.fixture
def client():
    store_snapshot_cache.clear_all()
    yield TestClient(create_app())
    store_snapshot_cache.clear_all()


def patch(client, body):
    return client.patch("/api/settings", params={"store_id": "s001"}, json=body)


def test_work_start_earlier_than_an_hour_before_opening_allows_early_alert(client):
    # 한림국수는 10:00 에 연다. 출근이 8:30 이면 8:40 알림도 받을 수 있다 (예전 규칙은 9:00 부터)
    slots = client.get("/api/settings", params={"store_id": "s001"}).json()["settings"]["slots"]
    assert patch(client, {"slots": {**slots, "OPENING": "08:40"}}).status_code == 400
    res = patch(client, {"work_hours": {"start": "08:30", "end": "22:00"}, "slots": {**slots, "OPENING": "08:40"}})
    assert res.status_code == 200
    body = res.json()["settings"]
    assert body["work_hours"] == {"start": "08:30", "end": "22:00"} and body["slots"]["OPENING"] == "08:40"


def test_extra_alerts_are_sorted_and_must_be_within_work_hours(client):
    res = patch(client, {"extra_slots": ["16:30", "11:00", "16:30"]})
    assert res.status_code == 200 and res.json()["settings"]["extra_slots"] == ["11:00", "16:30"]
    assert patch(client, {"extra_slots": ["07:00"]}).json()["error"]["code"] == "SLOT_OUTSIDE_OPEN_HOURS"
    assert patch(client, {"extra_slots": []}).json()["settings"]["extra_slots"] == []


def test_work_hours_must_end_after_start(client):
    assert patch(client, {"work_hours": {"start": "20:00", "end": "09:00"}}).status_code == 422


def test_busy_alert_is_saved_when_owner_confirms_and_stays_allowed(client):
    slots = client.get("/api/settings", params={"store_id": "s001"}).json()["settings"]["slots"]
    busy = {**slots, "AFTERNOON": "12:00"}  # 점심 바쁜 시간
    assert patch(client, {"slots": busy}).json()["error"]["code"] == "SLOT_IN_BUSY_DAYPART"
    res = patch(client, {"slots": busy, "allow_busy_slots": True})
    assert res.status_code == 200 and res.json()["settings"]["slots"]["AFTERNOON"] == "12:00"
    # 확인한 알림은 다음 저장 때도 막지 않는다
    assert patch(client, {"extra_slots": ["16:30"]}).status_code == 200
    # 시각을 다른 바쁜 시간으로 바꾸면 다시 묻는다
    assert patch(client, {"slots": {**slots, "AFTERNOON": "12:30"}}).json()["error"]["code"] == "SLOT_IN_BUSY_DAYPART"
