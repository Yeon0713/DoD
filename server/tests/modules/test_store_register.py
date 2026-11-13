"""매장 등록: 네이버 지도 가게 화면 읽기, 가게 표 한 줄 만들기, 목업 리뷰, 등록 API (네이버는 가짜 응답)."""

import dataclasses
import datetime as dt
import json

import pytest
from fastapi.testclient import TestClient

from app.core import naver_place
from app.core.naver_place import PlaceInfo, PlaceMenu, parse_place
from app.core.seoul_time import now_seoul
from app.data_pipeline import read_store_db, registered_stores
from app.main import create_app
from app.modules.stores import router as stores_router
from app.modules.stores.review_import import make_reviews

STATE = {
    "PlaceDetailBase:123456": {"name": "피플스클럽", "category": "돈가스", "roadAddress": "강원 춘천시 우석로67번길 12 1층",
                               "address": "강원 춘천시 석사동 742-10", "coordinate": {"x": "127.7516618", "y": "37.8653181"}, "visitorReviewsTotal": 201},
    "PlaceMenuItem:a": {"name": "로스카츠", "price": {"displayText": "12,500원"}, "images": [{"url": "https://img/1.jpg"}]},
    "PlaceMenuItem:b": {"name": "콜라", "price": {"displayText": "변동"}, "images": []},
    "ROOT_QUERY": {'placeDetail({"id":"123456"})': {"newBusinessHours": [{
        "freeText": "휴무일은 네이버소식란, 인스타 참고",
        "businessHours": [
            {"day": "월", "businessHours": {"start": "11:00", "end": "20:30"}, "breakHours": [{"start": "14:30", "end": "17:00"}]},
            {"day": "화", "businessHours": {"start": "11:00", "end": "20:30"}, "breakHours": [{"start": "14:30", "end": "17:00"}]},
            {"day": "토", "businessHours": {"start": "11:30", "end": "14:30"}, "breakHours": []},
        ]}]}},
}
HTML = f"<script>window.__APOLLO_STATE__ = {json.dumps(STATE, ensure_ascii=False)};window.__X = 1</script>"


def test_parse_place_reads_hours_break_menus():
    info = parse_place("123456", HTML)
    assert (info.name, info.category, info.road_address) == ("피플스클럽", "돈가스", "강원 춘천시 우석로67번길 12 1층")
    assert (info.lat, info.lng, info.review_total) == (37.8653181, 127.7516618, 201)
    assert info.weekly_hours["MON"] == {"open": "11:00", "close": "20:30"}
    assert info.weekly_hours["SAT"] == {"open": "11:30", "close": "14:30"}
    assert info.weekly_hours["SUN"] is None  # 화면에 없는 요일은 쉬는 날
    assert info.break_time == {"start": "14:30", "end": "17:00"}
    assert [(m.name, m.price, m.photo) for m in info.menus] == [("로스카츠", 12500, "https://img/1.jpg"), ("콜라", None, None)]
    assert info.closed_note == "휴무일은 네이버소식란, 인스타 참고"


def test_parse_place_fails_clearly_when_page_changes():
    with pytest.raises(naver_place.PlaceCrawlError):
        parse_place("123456", "<html>no data</html>")


def test_store_row_uses_common_hours_and_sets_alert_times():
    info = parse_place("123456", HTML)
    row = registered_stores.store_row("s101", info)
    assert (row["open_time"], row["close_time"]) == (dt.time(11, 0), dt.time(20, 30))
    assert row["closed_weekdays"] == ["WED", "THU", "FRI", "SUN"]
    assert row["slots"] == ["10:30", "15:00", "20:00"]  # 문 열기 30분 전, 브레이크 시작 30분 뒤, 닫기 30분 전


def test_menu_category_follows_db_rule():
    rows = registered_stores._menu_rows(parse_place("123456", HTML))
    assert [r["category"] for r in rows] == ["main", "drink"]


def test_mock_reviews_are_stable_and_make_today_tasks(monkeypatch):
    now = dt.datetime(2026, 11, 12, 18, 0, tzinfo=dt.timezone(dt.timedelta(hours=9)))
    monkeypatch.setattr("app.modules.stores.review_import.now_seoul", lambda: now)
    a = make_reviews("s101", "BAEMIN", ["로스카츠"], 11, 20)
    assert a == make_reviews("s101", "BAEMIN", ["로스카츠"], 11, 20)
    assert len(a) == 24 and all(r["written_at"] <= now for r in a)
    today_late = [r for r in a if r["written_at"].date() == now.date() and r["complaint_type"] == "delivery_delay"]
    assert len(today_late) == 1 and today_late[0]["written_at"].hour < 11  # 문 열기 전 불만 → 첫 알림에 사과 답글
    naver = make_reviews("s101", "NAVER", ["로스카츠"], 11, 20)
    assert not any(r["complaint_type"] == "delivery_delay" for r in naver)  # 매장 손님은 배달 불만이 없다


@pytest.fixture
def client(monkeypatch):
    info = parse_place("123456", HTML)
    monkeypatch.setattr(stores_router, "find_place_id", lambda *a, **k: "123456")
    monkeypatch.setattr(stores_router, "crawl_place", lambda place_id: info)
    stores_router._previews.clear()
    return TestClient(create_app())


def test_preview_reads_place_without_saving(client, monkeypatch):
    monkeypatch.setattr(stores_router.registered_stores, "store_for_place", lambda pid: None)
    monkeypatch.setattr(stores_router.registered_stores, "register", lambda info: pytest.fail("미리 보기는 저장하지 않아요"))
    body = client.post("/api/stores/preview", json={"name": "피플스클럽", "lat": 37.86, "lng": 127.75}).json()
    assert body["place"]["place_id"] == "123456" and body["registered_store_id"] is None


def test_register_saves_and_links_owner(client, monkeypatch):
    saved, owners = [], {}
    monkeypatch.setattr(stores_router.registered_stores, "register", lambda info: saved.append(info) or "s101")
    monkeypatch.setattr(stores_router.registered_stores, "set_owner", lambda key, sid: owners.update({key: sid}))
    monkeypatch.setattr(stores_router, "save_settings_changes", lambda sid, ch: None)
    monkeypatch.setattr(stores_router.demo_data, "fill", lambda *a, **k: {"orders": 0})
    body = client.post("/api/stores/register", json={"place_id": "123456", "owner_key": "naver:abc"}).json()
    assert body["store_id"] == "s101" and saved[0].name == "피플스클럽" and owners == {"naver:abc": "s101"}


def test_preview_explains_when_naver_cannot_be_read(client, monkeypatch):
    def fail(*a, **k):
        raise naver_place.PlaceCrawlError("네이버 지도 화면 모양이 바뀌었어요")

    monkeypatch.setattr(stores_router, "find_place_id", fail)
    res = client.post("/api/stores/preview", json={"name": "피플스클럽", "lat": 37.86, "lng": 127.75})
    assert res.status_code == 502 and res.json()["error"]["code"] == "PLACE_NOT_READ"


def test_import_rejects_unknown_platform_and_mock_store(client):
    assert client.post("/api/stores/s001/reviews/import", json={"platform": "BAEMIN"}).json()["error"]["code"] == "NOT_REGISTERED_STORE"


def test_mock_place_links_to_mock_store_and_marks_existing_reviews(client, tmp_path, monkeypatch):
    """피플스클럽(네이버 가게 id 1909851296)을 등록하면 새 파일 없이 s004 로 잇고, 리뷰 불러오기는 있는 리뷰만 표시한다."""
    monkeypatch.setattr(registered_stores, "REGISTRY_PATH", tmp_path / "registry.db")
    monkeypatch.setattr(stores_router, "save_settings_changes", lambda sid, ch: None)
    info = dataclasses.replace(parse_place("123456", HTML), place_id="1909851296")
    monkeypatch.setattr(stores_router, "crawl_place", lambda place_id: info)
    s004 = registered_stores.DATA_DIR / "s004.db"
    files_before, s004_before = sorted(registered_stores.DATA_DIR.glob("*.db")), s004.read_bytes()

    body = client.post("/api/stores/register", json={"place_id": "1909851296", "owner_key": "naver:abc"}).json()
    assert body["store_id"] == "s004" and registered_stores.store_for_owner("naver:abc") == "s004"

    reviews = read_store_db.read_reviews("s004", until=now_seoul())
    linked = sum(r["order_id"] is not None for r in reviews)
    coupang = sum(r.get("platform") == "COUPANG" for r in reviews)
    assert 0 < coupang < linked  # 배달 리뷰 일부가 쿠팡이츠
    imported = {p: client.post("/api/stores/s004/reviews/import", json={"platform": p}).json()["imported"] for p in ("BAEMIN", "NAVER", "COUPANG")}
    assert imported == {"BAEMIN": linked - coupang, "NAVER": len(reviews) - linked, "COUPANG": coupang}
    platforms = {r["review_id"]: r["platform"] for r in read_store_db.read_reviews("s004", until=now_seoul())}
    assert sum(p == "COUPANG" for p in platforms.values()) == coupang and None not in platforms.values()  # 불러온 뒤에도 같은 나눔
    assert client.post("/api/stores/s004/reviews/import", json={"platform": "BAEMIN"}).json()["already"] is True
    assert len(read_store_db.read_reviews("s004", until=now_seoul())) == len(reviews)  # 새 리뷰를 넣지 않는다

    client.post("/api/stores/s004/refresh")
    assert sorted(registered_stores.DATA_DIR.glob("*.db")) == files_before and s004.read_bytes() == s004_before  # 목업 파일은 그대로


def test_reset_all_removes_only_registered_store_files(tmp_path, monkeypatch):
    for name in ("s001.db", "s003.db", "s101.db", "s150.db", "common.db"):
        (tmp_path / name).touch()
    registry = tmp_path / "app_data" / "registry.db"
    registry.parent.mkdir()
    registry.touch()
    monkeypatch.setattr(registered_stores, "DATA_DIR", tmp_path)
    monkeypatch.setattr(registered_stores, "REGISTRY_PATH", registry)
    assert registered_stores.reset_all() == ["s101", "s150"]
    assert sorted(p.name for p in tmp_path.glob("*.db")) == ["common.db", "s001.db", "s003.db"]
    assert not registry.exists()
