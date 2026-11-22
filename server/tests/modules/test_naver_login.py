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
    assert "테스트" in page and "dona_demo" in page


def test_test_login_wrong_password_stays_on_page(client, monkeypatch):
    state = _mock_start(client, monkeypatch)
    page = client.post("/api/auth/naver/mock/login", data={"state": state, "login_id": "dona_demo", "password": "wrong"}).text
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


def test_demo_account_goes_to_store_registered_by_that_account(client, monkeypatch):
    """데모 계정은 정해 둔 가게 없이, 이 계정으로 등록해 둔 가게로 들어간다 (진짜 네이버 계정과 같다). 없으면 가게 찾기부터."""
    monkeypatch.setattr(settings, "dev_clock_enabled", False)
    monkeypatch.setattr(auth.registered_stores, "store_for_owner", lambda key: "s003" if key == "naver:TEST_NAVER_ID_DEMO" else None)
    body = _test_login(client, monkeypatch, "dona_demo")
    assert body["test"] is True and body["store_id"] == "s003"
    assert body["received"]["email"] == "dona_demo@example.com"
    assert body["test_account"] == {"login_id": "dona_demo", "on_logout": "keep", "scene_at": None}
    monkeypatch.setattr(auth.registered_stores, "store_for_owner", lambda key: None)
    assert _test_login(client, monkeypatch, "dona_demo")["store_id"] is None


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


def test_callback_returns_to_app_when_naver_sends_non_json(client, monkeypatch):
    """네이버가 JSON 이 아닌 응답(게이트웨이 오류 html 등)을 주면 500 화면에서 멈추지 않고 앱으로 돌려보낸다."""
    monkeypatch.setattr(auth.httpx, "get", lambda url, **kwargs: auth.httpx.Response(502, text="<html>Bad Gateway</html>"))
    state = parse_qs(urlparse(client.get("/api/auth/naver/start", params={"back": BACK}).headers["location"]).query)["state"][0]
    res = client.get("/api/auth/naver/callback", params={"state": state, "code": "c"})
    assert res.status_code == 302
    assert parse_qs(urlparse(res.headers["location"]).query)["error"] == ["NAVER_BAD_RESPONSE"]


def test_find_store_ignores_registered_store_and_store_id_wins(client, monkeypatch):
    """DB 에서 find_store 를 켜면 등록 기록이 있어도 가게 찾기부터, store_id 를 넣으면 그 가게로 들어간다."""
    monkeypatch.setattr(settings, "dev_clock_enabled", False)
    monkeypatch.setattr(auth.registered_stores, "store_for_owner", lambda key: "s003")
    with test_accounts._db() as conn:
        conn.execute("UPDATE test_accounts SET find_store = 1 WHERE login_id = 'dona_demo'")
    assert _test_login(client, monkeypatch, "dona_demo")["store_id"] is None
    with test_accounts._db() as conn:
        conn.execute("UPDATE test_accounts SET find_store = 0, store_id = 's001' WHERE login_id = 'dona_demo'")
    assert _test_login(client, monkeypatch, "dona_demo")["store_id"] == "s001"


def test_scene_account_moves_server_clock_on_login(client, monkeypatch):
    """DB 에 scene_at 을 넣은 계정은 로그인할 때 서버 시계를 그 시각으로 옮긴다 (DEV_CLOCK_ENABLED 일 때만)."""
    with test_accounts._db() as conn:
        conn.execute("UPDATE test_accounts SET store_id = 's001', scene_at = '2026-09-10T21:35:00+09:00' WHERE login_id = 'dona_demo'")
    monkeypatch.setattr(settings, "dev_clock_enabled", True)
    forgotten = []
    monkeypatch.setattr(auth.store_snapshot_cache, "forget", forgotten.append)
    try:
        body = _test_login(client, monkeypatch, "dona_demo")
        assert body["test_account"]["scene_at"] == "2026-09-10T21:35:00+09:00"
        assert abs((now_seoul() - dt.datetime(2026, 9, 10, 21, 35, tzinfo=SEOUL)).total_seconds()) < 5
        assert forgotten == ["s001"]
    finally:
        set_clock_shift(dt.timedelta(0))


def test_logout_reset_clears_store_and_clock_but_keep_does_not(client, monkeypatch):
    monkeypatch.setattr(settings, "dev_clock_enabled", True)
    monkeypatch.setattr(auth.registered_stores, "store_for_owner", lambda key: "s005")
    reset = []
    monkeypatch.setattr(auth.store_snapshot_cache, "reset_store", reset.append)
    try:
        set_clock_shift(dt.timedelta(days=-60))
        assert client.post("/api/auth/test/logout", json={"login_id": "dona_demo"}).json()["on_logout"] == "keep"
        assert reset == [] and clock_shift() == dt.timedelta(days=-60)  # keep: 그대로
        with test_accounts._db() as conn:
            conn.execute("UPDATE test_accounts SET on_logout = 'reset' WHERE login_id = 'dona_demo'")
        assert client.post("/api/auth/test/logout", json={"login_id": "dona_demo"}).json()["on_logout"] == "reset"
        assert reset == ["s005"] and clock_shift() == dt.timedelta(0)  # reset: 그 가게와 시계를 처음으로
    finally:
        set_clock_shift(dt.timedelta(0))
    assert client.post("/api/auth/test/logout", json={"login_id": "nobody"}).status_code == 404


def test_withdraw_unlinks_store_but_keeps_account_and_store_data(client, monkeypatch, tmp_path):
    """탈퇴: 계정과 가게 연결을 끊고 리뷰 불러오기 기록을 비운다. 같은 아이디로 다시 로그인하면 가게 찾기(가입)부터, 가게의 등록 기록은 남는다."""
    registry = auth.registered_stores
    monkeypatch.setattr(registry, "REGISTRY_PATH", tmp_path / "registry.db")
    monkeypatch.setattr(registry, "DATA_DIR", tmp_path)
    (tmp_path / "s005.db").touch()
    monkeypatch.setattr(auth, "list_store_ids", lambda: ["s005"])
    monkeypatch.setattr(auth, "read_store", lambda store_id: {"name": "초옹장"})
    monkeypatch.setattr(settings, "dev_clock_enabled", False)
    with registry._db() as conn:
        conn.execute("INSERT INTO stores VALUES ('s005', '2004174048', '{}', 'now', 'now')")
    registry.set_owner("naver:TEST_NAVER_ID_DEMO", "s005")
    registry.mark_platform("s005", "BAEMIN", [1, 2])
    reset, revoked = [], []
    monkeypatch.setattr(auth.store_snapshot_cache, "reset_store", reset.append)
    from app.modules.owner_check import review as owner_check
    monkeypatch.setattr(owner_check, "withdraw", revoked.append)
    assert _test_login(client, monkeypatch, "dona_demo")["store_id"] == "s005"

    body = client.post("/api/auth/test/withdraw", json={"login_id": "dona_demo"}).json()
    assert body == {"login_id": "dona_demo", "unlinked_store_id": "s005"} and reset == ["s005"]
    assert revoked == ["naver:TEST_NAVER_ID_DEMO"]  # 사장님 확인 승인도 거둔다 → 다시 가입하면 다시 확인
    assert _test_login(client, monkeypatch, "dona_demo")["store_id"] is None  # 다시 가입부터
    assert test_accounts.by_login_id("dona_demo") is not None  # 계정은 그대로
    assert registry.store_for_place("2004174048") == "s005"  # 가게 등록 기록은 그대로
    assert registry.imported_counts("s005") == {}  # 목업 가게로 이은 가게는 리뷰 불러오기 기록을 비운다 → 다시 가입하면 불러오기부터
    assert client.post("/api/auth/test/withdraw", json={"login_id": "dona_demo"}).json()["unlinked_store_id"] is None
    assert client.post("/api/auth/test/withdraw", json={"login_id": "nobody"}).status_code == 404


def test_test_accounts_db_is_made_with_defaults_and_edits_apply(tmp_path):
    assert not test_accounts.DB_PATH.exists()
    assert [a["login_id"] for a in test_accounts.all_accounts()] == ["dona_demo"]
    assert test_accounts.DB_PATH.exists()
    with test_accounts._db() as conn:
        conn.execute("UPDATE test_accounts SET on_logout = 'reset' WHERE login_id = 'dona_demo'")
    assert test_accounts.by_login_id("dona_demo")["on_logout"] == "reset"  # 서버를 다시 켜지 않아도 바로


def test_only_cors_origins_are_accepted(client, monkeypatch):
    """CORS_ORIGINS 에 있는 주소(3000, localhost:8082, 127.0.0.1:8082)만 로그인 뒤 돌아갈 주소와 요청을 받는다. 같은 컴퓨터라도 다른 포트는 막는다."""
    monkeypatch.setattr(settings, "naver_login_client_id", "")
    assert settings.cors_origin_regex == ""
    for origin in ("http://localhost:3000", "http://localhost:8082", "http://127.0.0.1:8082"):
        assert client.get("/api/auth/naver/start", params={"back": f"{origin}/start/naver-login"}).status_code == 302
        assert client.get("/health", headers={"Origin": origin}).headers["access-control-allow-origin"] == origin
    for origin in ("http://localhost:8081", "http://localhost:8092", "http://127.0.0.1:3000", "http://localhost:19006"):
        assert client.get("/api/auth/naver/start", params={"back": f"{origin}/start/naver-login"}).json()["error"]["code"] == "BAD_BACK_URL"
        assert "access-control-allow-origin" not in client.get("/health", headers={"Origin": origin}).headers


def test_other_sites_are_still_refused(client, monkeypatch):
    monkeypatch.setattr(settings, "naver_login_client_id", "")
    for origin in ("http://evil.example.com", "http://localhost.evil.example.com:8082", "https://localhost:8082"):
        assert client.get("/api/auth/naver/start", params={"back": f"{origin}/start"}).json()["error"]["code"] == "BAD_BACK_URL"
        assert "access-control-allow-origin" not in client.get("/health", headers={"Origin": origin}).headers


def test_health_tells_whether_server_is_in_dev_mode(client, monkeypatch):
    assert client.get("/health").json()["dev_mode"] is settings.dev_clock_enabled


def test_test_account_list_says_store_and_what_happens(client, monkeypatch):
    """임시 네이버 로그인의 테스트 계정 목록: 어느 가게로 들어가고 무엇을 시험하는지 보인다 (DB 의 scenario)."""
    with test_accounts._db() as conn:
        conn.execute("UPDATE test_accounts SET store_id = 's001' WHERE login_id = 'dona_demo'")
    state = _mock_start(client, monkeypatch)
    page = client.get(f"/api/auth/naver/mock/login?state={state}").text
    assert "사장님 1" not in page
    assert "탈퇴하면 다시 가입부터" in page
    assert "dona_demo" in page
