"""우리 가게 찾기: 네이버 지역 검색과 고른 가게 저장 (app/modules/naver). 네이버 검색은 가짜 응답으로 바꿔 끼운다."""

import pytest
from fastapi.testclient import TestClient

from app.data_pipeline import store_snapshot_cache
from app.main import create_app
from app.modules.naver import data_provider


class Answer:
    def __init__(self, status, body):
        self.status_code = status
        self.body = body

    def json(self):
        return self.body


ITEMS = [
    {"title": "피플스<b>클럽</b>", "category": "음식점>일식>돈가스", "address": "강원특별자치도 춘천시 석사동 742-10 1층",
     "roadAddress": "강원특별자치도 춘천시 우석로67번길 12 1층", "mapx": "1277516618", "mapy": "378653181"},
    {"title": "좌표 없는 곳", "category": "음식점", "address": "어딘가"},
]


@pytest.fixture
def client(monkeypatch):
    store_snapshot_cache.clear_all()
    monkeypatch.setattr(data_provider.api_hub, "get", lambda path, params=None: Answer(200, {"items": ITEMS}))
    yield TestClient(create_app())
    store_snapshot_cache.clear_all()


def test_search_cleans_names_and_reads_coordinates(client):
    body = client.get("/api/naver/search", params={"query": "춘천 돈가스"}).json()
    assert body["items"] == [
        {"name": "피플스클럽", "category": "돈가스", "address": "강원특별자치도 춘천시 우석로67번길 12 1층",
         "jibun_address": "강원특별자치도 춘천시 석사동 742-10 1층", "lat": 37.8653181, "lng": 127.7516618}
    ]


def test_short_query_does_not_call_naver(client, monkeypatch):
    monkeypatch.setattr(data_provider.api_hub, "get", lambda *a, **k: pytest.fail("네이버를 부르면 안 돼요"))
    assert client.get("/api/naver/search", params={"query": "돈"}).json() == {"items": []}


def test_search_failure_is_explained(client, monkeypatch):
    monkeypatch.setattr(data_provider.api_hub, "get", lambda *a, **k: Answer(401, {}))
    res = client.get("/api/naver/search", params={"query": "춘천 돈가스"})
    assert res.status_code == 502 and res.json()["error"]["code"] == "NAVER_SEARCH_FAILED"


def test_place_shows_real_store_address_without_test_mark(client):
    place = client.get("/api/naver/place", params={"store_id": "s003"}).json()["place"]
    assert place["name"] == "석사돈가스"
    assert "석사동" in place["address"] and "가상" not in place["address"]
