"""데모 테스트 모드 네이버 로그인 (app/modules/auth/router.py). 네이버는 가짜 응답으로 바꿔 끼운다."""

import datetime as dt
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.seoul_time import SEOUL, clock_shift, now_seoul, set_clock_shift
from app.main import create_app
from app.modules.auth import router as auth
from app.modules.auth import test_accounts

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


def _test_login(client, monkeypatch, login_id: str) -> dict:
    """임시 네이버 로그인으로 들어가 서버가 앱에 넘기는 결과를 받는다."""
    state = _mock_start(client, monkeypatch)
    res = client.post("/api/auth/naver/mock/login", data={"state": state, "login_id": login_id, "password": "dona1234"})
    assert res.status_code == 303  # 동의 화면 없이 바로 callback 으로
    res = client.get(res.headers["location"])
    assert res.headers["location"].startswith(BACK + "?ticket=")
    ticket = parse_qs(urlparse(res.headers["location"]).query)["ticket"][0]
    return client.get(f"/api/auth/naver/result/{ticket}").json()


@pytest.mark.parametrize(
    ("login_id", "store_id", "on_logout"),
    [("dona_test1", None, "reset"), ("dona_test2", "s001", "reset"), ("dona_test3", "s003", "keep")],
)
def test_test_accounts_follow_db_conditions(client, monkeypatch, login_id, store_id, on_logout):
    """test1 은 등록해 둔 가게가 있어도 늘 가게 찾기부터(store_id 없음), test2·3 은 DB 에 정해 둔 가게로 들어간다."""
    monkeypatch.setattr(auth.registered_stores, "store_for_owner", lambda key: "s002")  # 등록 기록이 있어도
    monkeypatch.setattr(settings, "dev_clock_enabled", False)
    body = _test_login(client, monkeypatch, login_id)
    assert body["test"] is True
    assert body["store_id"] == store_id
    assert body["received"]["email"] == f"{login_id}@example.com"
    assert body["test_account"] == {"login_id": login_id, "on_logout": on_logout, "scene_at": None}


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
    """DB 에서 가게 찾기(find_store)를 끄고 가게(store_id)를 비우면, 그 계정으로 등록해 둔 가게로 들어간다 (진짜 네이버 계정과 같다)."""
    with test_accounts._db() as conn:
        conn.execute("UPDATE test_accounts SET find_store = 0, store_id = NULL WHERE login_id = 'dona_test1'")
    monkeypatch.setattr(auth.registered_stores, "store_for_owner", lambda key: "s003" if key == "naver:TEST_NAVER_ID_0001" else None)
    assert _test_login(client, monkeypatch, "dona_test1")["store_id"] == "s003"


def test_scene_account_moves_server_clock_on_login(client, monkeypatch):
    """test2 는 DB 의 scene_at(할 일이 몰리는 9/10 21:35)으로 서버 시계를 옮긴다 (DEV_CLOCK_ENABLED 일 때만)."""
    monkeypatch.setattr(settings, "dev_clock_enabled", True)
    forgotten = []
    monkeypatch.setattr(auth.store_snapshot_cache, "forget", forgotten.append)
    try:
        body = _test_login(client, monkeypatch, "dona_test2")
        assert body["test_account"]["scene_at"] == "2026-09-10T21:35:00+09:00"
        assert abs((now_seoul() - dt.datetime(2026, 9, 10, 21, 35, tzinfo=SEOUL)).total_seconds()) < 5
        assert forgotten == ["s001"]
    finally:
        set_clock_shift(dt.timedelta(0))


def test_logout_reset_clears_store_and_clock_but_keep_does_not(client, monkeypatch):
    monkeypatch.setattr(settings, "dev_clock_enabled", True)
    reset = []
    monkeypatch.setattr(auth.store_snapshot_cache, "reset_store", reset.append)
    try:
        set_clock_shift(dt.timedelta(days=-60))
        assert client.post("/api/auth/test/logout", json={"login_id": "dona_test3"}).json()["on_logout"] == "keep"
        assert reset == [] and clock_shift() == dt.timedelta(days=-60)  # keep: 그대로
        assert client.post("/api/auth/test/logout", json={"login_id": "dona_test2"}).json()["on_logout"] == "reset"
        assert reset == ["s001"] and clock_shift() == dt.timedelta(0)  # reset: 그 가게와 시계를 처음으로
    finally:
        set_clock_shift(dt.timedelta(0))
    assert client.post("/api/auth/test/logout", json={"login_id": "nobody"}).status_code == 404


def test_test_accounts_db_is_made_with_defaults_and_edits_apply(tmp_path):
    assert not test_accounts.DB_PATH.exists()
    assert [a["login_id"] for a in test_accounts.all_accounts()] == ["dona_test1", "dona_test2", "dona_test3"]
    assert test_accounts.DB_PATH.exists()
    with test_accounts._db() as conn:
        conn.execute("UPDATE test_accounts SET on_logout = 'keep' WHERE login_id = 'dona_test2'")
    assert test_accounts.by_login_id("dona_test2")["on_logout"] == "keep"  # 서버를 다시 켜지 않아도 바로


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


def test_test_account_list_says_store_and_what_happens(client, monkeypatch):
    """임시 네이버 로그인의 테스트 계정 목록: '사장님 1' 이 아니라 어느 가게로 들어가고 무엇을 시험하는지 보인다 (DB 의 scenario)."""
    state = _mock_start(client, monkeypatch)
    page = client.get(f"/api/auth/naver/mock/login?state={state}").text
    assert "사장님 1" not in page
    assert "로그인할 때마다 네이버 지도에서 가게 찾기" in page
    assert "한림국수 (s001)" in page and "석사돈가스 (s003)" in page
