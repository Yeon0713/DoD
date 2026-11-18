"""가입·로그인 (voice/api/account.py): 메인 서버의 /api 모듈을 이 서버에 붙였는지, 등록 가게를 이 서버에 만드는지.

메인 데이터(server/db/data, server/db/app_data/registry.db)는 읽기만 한다. 쓰는 것은 이 테스트의 임시 voice.db 뿐이다.
"""

from fastapi.testclient import TestClient

from voice import repo
from voice.main import create_app


def client() -> TestClient:
    return TestClient(create_app())


def test_config_and_mounted_modules():
    c = client()
    assert c.get("/v1/account/config").json()["demo_store_id"] == "s005"
    assert c.get("/api/owner_check/sample", params={"store_id": "s005"}).json()["owner_name"] == "김도나"
    assert c.get("/api/naver/place", params={"store_id": "s005"}).json()["place"]["name"] == "초옹장"


def test_naver_login_returns_only_to_known_apps():
    c = client()
    ok = c.get("/api/auth/naver/start", params={"back": "http://localhost:8090/join/naver-login"}, follow_redirects=False)
    assert ok.status_code == 302 and "/api/auth/naver/" in ok.headers["location"]
    bad = c.get("/api/auth/naver/start", params={"back": "http://evil.example/x"}, follow_redirects=False)
    assert bad.status_code == 400 and bad.json()["error"]["code"] == "BAD_BACK_URL"


def test_enter_builds_a_registered_store_from_main_data():
    c = client()
    assert repo.store("s101") is None
    entered = c.post("/v1/account/enter", json={"store_id": "s101"}).json()
    assert entered["store_id"] == "s101" and entered["name"]
    store = repo.store("s101")
    assert len(store["naver_hours"]) == 7 and store["menus"]
    assert c.get("/v1/home", params={"store_id": "s101"}).json()["store"]["name"] == entered["name"]
    assert c.get("/v1/settings", params={"store_id": "s101"}).json()["hours"]["days"][0]["label"] == "월"
    # 이미 있는 가게(시연 가게처럼)는 그대로 둔다
    again = c.post("/v1/account/enter", json={"store_id": "s101"}).json()
    assert again == entered


def test_enter_unknown_store():
    assert client().post("/v1/account/enter", json={"store_id": "s999"}).status_code == 404
