"""예약·단체 주문 (네이버 예약 동기화 목업 + 직접 적기)과 이번 주 바쁨 반영, 포스터용 가게 사진·로고."""

import base64
import datetime as dt
import json

import pytest
from fastapi.testclient import TestClient

from app.core import naver_place
from app.core.seoul_time import SEOUL
from app.data_pipeline import registered_stores, reservations, store_logo
from app.data_pipeline.db_rows_to_analysis_inputs import build_analysis_inputs
from app.data_pipeline.reservation_effect import apply_reservations, per_person_amount
from app.main import create_app
from app.planner.data_shapes import CalendarCell

AT = lambda *a: dt.datetime(*a, tzinfo=SEOUL)  # noqa: E731


@pytest.fixture(autouse=True)
def separate_registry(tmp_path, monkeypatch):
    monkeypatch.setattr(registered_stores, "REGISTRY_PATH", tmp_path / "registry.db")


@pytest.fixture
def client():
    return TestClient(create_app())


def test_naver_reservations_are_synced_once_and_listed_by_date():
    assert reservations.sync_from_naver("s005") == 4
    assert reservations.sync_from_naver("s005") == 0  # 한 번만
    week = reservations.list_reservations("s005", dt.date(2026, 10, 5), dt.date(2026, 10, 11))
    assert [(r["at"].date().isoformat(), r["people"], r["status"]) for r in week] == [
        ("2026-10-06", 4, "CONFIRMED"), ("2026-10-08", 15, "REQUESTED"), ("2026-10-09", 20, "CONFIRMED"),
    ]
    assert {r["source"] for r in week} == {"NAVER"}
    assert reservations.list_reservations("s001") == []  # 시험 데이터 없는 가게


def test_confirmed_reservation_makes_that_daypart_busy():
    """확정한 단체 예약은 인원 × 1인 평균 금액만큼 그 시간대 예상 매출에 더해지고, 비율이 1.15 를 넘으면 '많음'이 된다."""
    now = AT(2026, 10, 7, 15, 5)
    inputs = build_analysis_inputs("s005", now)
    person = per_person_amount(inputs, now)
    assert 7000 <= person <= 20000  # 국수집 한 그릇 값 언저리
    cell = CalendarCell(date=dt.date(2026, 10, 8), daypart="DINNER", signal="NORMAL", baseline_sales=600000, expected_sales=600000,
                        ratio=1.0, reasons=[], reason_text="", computed_at=now)
    rows = [{"reservation_id": 7, "kind": "RESERVATION", "at": AT(2026, 10, 8, 18, 30), "people": 15, "status": "REQUESTED"}]
    assert apply_reservations([cell], rows, inputs, now) == [cell]  # 문의(아직 안 받음)는 넣지 않는다
    rows[0]["status"] = "CONFIRMED"
    [busy] = apply_reservations([cell], rows, inputs, now)
    assert busy.expected_sales == 600000 + 15 * person
    assert busy.signal == "HIGH" and busy.ratio == round(busy.expected_sales / 600000, 2)
    assert busy.reasons[-1].tag == "RESERVATION" and busy.reason_text == "단체 예약 15명이 있어요"
    other = cell.model_copy(update={"daypart": "LUNCH"})
    assert apply_reservations([other], rows, inputs, now) == [other]  # 다른 시간대는 그대로


def test_overnight_store_early_morning_reservation_goes_to_previous_business_day():
    """17:00~03:00 가게(s002)의 11/22 01:00 예약은 11/21 영업일(11/21 17시~11/22 03시) 밤 칸에 더한다. 11/22 칸은 그대로."""
    now = AT(2026, 11, 20, 15, 0)
    inputs = build_analysis_inputs("s002", now)
    cells = [
        CalendarCell(date=day, daypart="NIGHT", signal="NORMAL", baseline_sales=500000, expected_sales=500000,
                     ratio=1.0, reasons=[], reason_text="", computed_at=now)
        for day in (dt.date(2026, 11, 21), dt.date(2026, 11, 22))
    ]
    rows = [{"reservation_id": 9, "kind": "RESERVATION", "at": AT(2026, 11, 22, 1, 0), "people": 10, "status": "CONFIRMED"}]
    saturday, sunday = apply_reservations(cells, rows, inputs, now)
    assert saturday.expected_sales == 500000 + 10 * per_person_amount(inputs, now)
    assert sunday == cells[1]


def test_reservation_api_flow(client):
    """목록(네이버 동기화) → 문의 받기 → 직접 적기 → 직접 적은 것만 지우기"""
    listed = client.get("/api/reservations", params={"store_id": "s005", "from": "2026-10-05", "to": "2026-10-11"}).json()["reservations"]
    asked = next(r for r in listed if r["status"] == "REQUESTED")
    assert asked["source_label"] == "네이버 예약" and asked["people"] == 15
    assert client.post(f"/api/reservations/{asked['reservation_id']}/confirm", params={"store_id": "s005"}).json()["status"] == "CONFIRMED"
    mine = client.post("/api/reservations", params={"store_id": "s005"},
                       json={"at": "2026-10-10T12:30:00+09:00", "people": 8, "kind": "GROUP_ORDER", "memo": "전화 주문"}).json()
    assert (mine["source"], mine["status"], mine["kind"]) == ("OWNER", "CONFIRMED", "GROUP_ORDER")
    assert client.delete(f"/api/reservations/{asked['reservation_id']}", params={"store_id": "s005"}).json()["error"]["code"] == "NAVER_RESERVATION"
    assert client.delete(f"/api/reservations/{mine['reservation_id']}", params={"store_id": "s005"}).json()["status"] == "CANCELED"
    ids = [r["reservation_id"] for r in client.get("/api/reservations", params={"store_id": "s005"}).json()["reservations"]]
    assert mine["reservation_id"] not in ids  # 지운 것은 목록에 없다
    bad = client.post("/api/reservations", params={"store_id": "s005"}, json={"at": "2026-10-10T12:30:00+09:00", "people": 0})
    assert bad.status_code == 422


def test_reservation_cannot_be_changed_from_other_store(client):
    asked = next(r for r in client.get("/api/reservations", params={"store_id": "s005"}).json()["reservations"] if r["status"] == "REQUESTED")
    res = client.post(f"/api/reservations/{asked['reservation_id']}/confirm", params={"store_id": "s001"})
    assert res.status_code == 404 and res.json()["error"]["code"] == "NOT_FOUND"
    assert reservations.get(asked["reservation_id"])["status"] == "REQUESTED"  # 바뀌지 않았다


def test_canceled_or_declined_reservation_cannot_be_confirmed(client):
    store = {"store_id": "s005"}
    mine = client.post("/api/reservations", params=store, json={"at": "2026-10-10T12:30:00+09:00", "people": 8}).json()
    assert client.delete(f"/api/reservations/{mine['reservation_id']}", params=store).json()["status"] == "CANCELED"
    again = client.post(f"/api/reservations/{mine['reservation_id']}/confirm", params=store)
    assert again.status_code == 422 and again.json()["error"]["code"] == "BAD_TRANSITION"

    asked = next(r for r in client.get("/api/reservations", params=store).json()["reservations"] if r["status"] == "REQUESTED")
    assert client.post(f"/api/reservations/{asked['reservation_id']}/decline", params=store).json()["status"] == "DECLINED"
    assert client.post(f"/api/reservations/{asked['reservation_id']}/decline", params=store).json()["status"] == "DECLINED"  # 두 번 눌러도 그대로
    again = client.post(f"/api/reservations/{asked['reservation_id']}/confirm", params=store)
    assert again.status_code == 422 and again.json()["error"]["code"] == "BAD_TRANSITION"


def test_status_change_loses_if_status_changed_meanwhile(monkeypatch):
    """읽은 뒤 다른 요청이 먼저 DECLINED 로 바꿨으면, 늦게 온 CONFIRMED 는 덮지 않고 거절한다."""
    asked = next(r for r in reservations.list_reservations("s005") if r["status"] == "REQUESTED")
    real_get = reservations.get
    reservations.set_status(asked["reservation_id"], "DECLINED")  # 다른 기기가 먼저 바꿈
    monkeypatch.setattr(reservations, "get", lambda _id: asked)  # 이쪽은 아직 REQUESTED 로 읽었다
    with pytest.raises(reservations.ReservationError) as err:
        reservations.set_status(asked["reservation_id"], "CONFIRMED")
    assert err.value.code == "BAD_TRANSITION"
    assert real_get(asked["reservation_id"])["status"] == "DECLINED"  # 그대로


def test_same_status_again_still_succeeds():
    asked = next(r for r in reservations.list_reservations("s005") if r["status"] == "REQUESTED")
    assert reservations.set_status(asked["reservation_id"], "CONFIRMED")["status"] == "CONFIRMED"
    assert reservations.set_status(asked["reservation_id"], "CONFIRMED")["status"] == "CONFIRMED"  # 두 번 눌러도 그대로


def _state_html(state: dict) -> str:
    return f"<script>window.__APOLLO_STATE__ = {json.dumps(state, ensure_ascii=False)};window.__X = 1</script>"


def test_place_photos_profile_and_facilities_are_read():
    """사장님이 올린 매장 사진(business)과 대표 사진은 읽고, 손님 사진(visitor)은 넣지 않는다."""
    state = {
        "PlaceDetailBase:1": {"name": "가게", "conveniences": ["단체 이용 가능", "예약"], "coordinate": {"x": "127", "y": "37"}},
        "PlaceDetailTopPhotoItem:1_business_1": {"mediaSource": "business", "mediaFormat": "image", "originalUrl": "https://a.pstatic.net/rep.jpg"},
        "PlaceDetailTopPhotoItem:1_business_2": {"mediaSource": "business", "mediaFormat": "image", "originalUrl": "https://a.pstatic.net/hall.jpg"},
        "PlaceDetailTopPhotoItem:1_visitor_1": {"mediaSource": "visitor", "mediaFormat": "image", "originalUrl": "https://a.pstatic.net/guest.jpg"},
        "ROOT_QUERY": {'placeDetail({"id":"1"})': {"images": {"images": [{"origin": "https://a.pstatic.net/rep.jpg"}]}}},
    }
    info = naver_place.parse_place("1", _state_html(state))
    assert info.photos == ["https://a.pstatic.net/rep.jpg", "https://a.pstatic.net/hall.jpg"]
    assert info.profile_photo == "https://a.pstatic.net/rep.jpg" and info.logo is None
    assert info.facilities == ["단체 이용 가능", "예약"]
    assert naver_place.PlaceInfo.from_dict({k: v for k, v in info.to_dict().items() if k not in ("photos", "profile_photo", "logo", "facilities")}).photos == []  # 예전에 저장한 정보도 읽힌다


def test_logo_upload_and_image_proxy_rules(client, logo_png):
    png = "data:image/png;base64," + base64.b64encode(logo_png).decode()
    assert client.get("/api/stores/s005/logo").json()["error"]["code"] == "NO_LOGO"
    body = client.post("/api/stores/s005/logo", json={"data_url": png}).json()
    assert body["logo"].startswith("/api/stores/s005/logo?v=") and body["logo_source"] == "OWNER"
    res = client.get("/api/stores/s005/logo")
    assert res.headers["content-type"] == "image/png" and res.content.startswith(b"\x89PNG")
    assert client.post("/api/stores/s005/logo", json={"data_url": "data:text/html;base64,PGI+"}).json()["error"]["code"] == "BAD_LOGO"
    broken = "data:image/png;base64," + base64.b64encode(b"\x89PNG\r\n\x1a\n-not-an-image").decode()
    assert client.post("/api/stores/s005/logo", json={"data_url": broken}).json()["error"]["code"] == "BAD_LOGO"
    assert client.delete("/api/stores/s005/logo").json() == {"removed": True, "logo": None, "logo_source": None}
    # 사진 대신 받기는 네이버 사진(pstatic.net)만
    for bad in ("https://evil.example.com/a.jpg", "http://a.pstatic.net/a.jpg", "https://pstatic.net.evil.com/a.jpg"):
        assert client.get("/api/stores/image", params={"url": bad}).json()["error"]["code"] == "BAD_IMAGE_URL"
