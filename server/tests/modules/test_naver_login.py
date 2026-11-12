"""데모 테스트 모드 네이버 로그인 (app/modules/auth/router.py). 네이버는 가짜 응답으로 바꿔 끼운다."""

from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import create_app
from app.modules.auth import router as auth

BACK = "http://localhost:8082/start/demo"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(settings, "naver_login_client_id", "test-id")
    monkeypatch.setattr(settings, "naver_login_client_secret", "test-secret")
    auth._pending.clear()
    auth._results.clear()
    auth._mock_codes.clear()
    return TestClient(create_app(), follow_redirects=False)


def _mock_start(client, monkeypatch) -> str:
    monkeypatch.setattr(settings, "naver_login_client_id", "")
    res = client.get("/api/auth/naver/start", params={"back": BACK})
    assert res.status_code == 302
    assert res.headers["location"].startswith("/api/auth/naver/mock/login?state=")
    return parse_qs(urlparse(res.headers["location"]).query)["state"][0]


def test_without_keys_goes_to_test_login_page(client, monkeypatch):
    state = _mock_start(client, monkeypatch)
    page = client.get("/api/auth/naver/mock/login", params={"state": state}).text
    assert "테스트" in page and "dona_test1" in page


def test_test_login_wrong_password_stays_on_page(client, monkeypatch):
    state = _mock_start(client, monkeypatch)
    page = client.post("/api/auth/naver/mock/login", data={"state": state, "login_id": "dona_test1", "password": "wrong"}).text
    assert "잘못 입력했어요" in page
    assert not auth._mock_codes


@pytest.mark.parametrize("login_id", ["dona_test1", "dona_test2", "dona_test3"])
def test_test_login_gives_profile_without_store(client, monkeypatch, login_id):
    """네이버 로그인으로는 가게를 알 수 없다. 등록해 둔 가게가 없으면 store_id 가 비어 있다."""
    monkeypatch.setattr(auth.registered_stores, "store_for_owner", lambda key: None)
    state = _mock_start(client, monkeypatch)
    res = client.post("/api/auth/naver/mock/login", data={"state": state, "login_id": login_id, "password": "dona1234"})
    assert res.status_code == 303  # 동의 화면 없이 바로 callback 으로
    res = client.get(res.headers["location"])
    assert res.headers["location"].startswith(BACK + "?ticket=")
    ticket = parse_qs(urlparse(res.headers["location"]).query)["ticket"][0]
    body = client.get(f"/api/auth/naver/result/{ticket}").json()
    assert body["test"] is True
    assert body["store_id"] is None
    assert body["received"]["email"] == f"{login_id}@example.com"


def test_start_refuses_unknown_back_url(client):
    res = client.get("/api/auth/naver/start", params={"back": "https://evil.example/x"})
    assert res.status_code == 400


def test_start_sends_to_naver_with_state(client):
    res = client.get("/api/auth/naver/start", params={"back": BACK})
    url = urlparse(res.headers["location"])
    query = parse_qs(url.query)
    assert url.netloc == "nid.naver.com"
    assert query["client_id"] == ["test-id"]
    assert query["state"][0] in auth._pending


def test_callback_with_unknown_state_is_refused(client):
    assert client.get("/api/auth/naver/callback", params={"state": "nope", "code": "c"}).status_code == 400


def test_callback_cancelled_returns_error_to_app(client):
    state = parse_qs(urlparse(client.get("/api/auth/naver/start", params={"back": BACK}).headers["location"]).query)["state"][0]
    res = client.get("/api/auth/naver/callback", params={"state": state, "error": "access_denied", "error_description": "Canceled By User"})
    assert parse_qs(urlparse(res.headers["location"]).query)["error"] == ["access_denied"]


def test_callback_success_keeps_token_on_server(client, monkeypatch):
    monkeypatch.setattr(auth.registered_stores, "store_for_owner", lambda key: None)
    class Answer:
        def __init__(self, body):
            self.body = body

        def json(self):
            return self.body

    def fake_get(url, **kwargs):
        if url == auth.TOKEN_URL:
            return Answer({"access_token": "secret-token", "expires_in": "3600"})
        return Answer({"resultcode": "00", "message": "success", "response": {"id": "abc", "name": "홍길동", "email": "a@b.c"}})

    monkeypatch.setattr(auth.httpx, "get", fake_get)
    state = parse_qs(urlparse(client.get("/api/auth/naver/start", params={"back": BACK}).headers["location"]).query)["state"][0]
    res = client.get("/api/auth/naver/callback", params={"state": state, "code": "c"})
    ticket = parse_qs(urlparse(res.headers["location"]).query)["ticket"][0]

    body = client.get(f"/api/auth/naver/result/{ticket}").json()
    assert body["received"] == {"id": "abc", "name": "홍길동", "email": "a@b.c"}
    assert body["test"] is False
    assert "nickname" in body["missing"] and "name" not in body["missing"]
    assert "secret-token" not in str(body)


def test_login_returns_store_registered_by_that_account(client, monkeypatch):
    monkeypatch.setattr(auth.registered_stores, "store_for_owner", lambda key: "s003" if key == "naver:TEST_NAVER_ID_0001" else None)
    state = _mock_start(client, monkeypatch)
    res = client.post("/api/auth/naver/mock/login", data={"state": state, "login_id": "dona_test1", "password": "dona1234"})
    res = client.get(res.headers["location"])
    ticket = parse_qs(urlparse(res.headers["location"]).query)["ticket"][0]
    assert client.get(f"/api/auth/naver/result/{ticket}").json()["store_id"] == "s003"


def test_app_on_this_computer_is_accepted_on_any_port(client, monkeypatch):
    """앱을 8081 같은 다른 포트로 켜거나, 예전 .env 의 CORS_ORIGINS 에 8082 가 없어도 로그인과 요청이 된다."""
    monkeypatch.setattr(settings, "naver_login_client_id", "")
    monkeypatch.setattr(settings, "cors_origins", ["http://localhost:3000"])
    for origin in ("http://localhost:8081", "http://127.0.0.1:8082", "http://localhost:19006"):
        assert client.get("/api/auth/naver/start", params={"back": f"{origin}/start/naver-login"}).status_code == 302
        assert client.get("/health", headers={"Origin": origin}).headers["access-control-allow-origin"] == origin


def test_other_sites_are_still_refused(client, monkeypatch):
    monkeypatch.setattr(settings, "naver_login_client_id", "")
    for origin in ("http://evil.example.com", "http://localhost.evil.example.com:8082", "https://localhost:8082"):
        assert client.get("/api/auth/naver/start", params={"back": f"{origin}/start"}).json()["error"]["code"] == "BAD_BACK_URL"
        assert "access-control-allow-origin" not in client.get("/health", headers={"Origin": origin}).headers


def test_health_tells_whether_server_is_in_dev_mode(client, monkeypatch):
    assert client.get("/health").json()["dev_mode"] is settings.dev_clock_enabled
