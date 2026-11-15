"""사장님 확인 심사 (app/modules/owner_check, 목업 국세청). 시험용 값은 db/mock_business_registrations.json."""

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.data_pipeline import registered_stores
from app.main import create_app
from app.modules.owner_check import mock_nts, review
from app.modules.owner_check import router as owner_router

CHOONG = {"business_no": "120-81-03450", "owner_name": "김도나", "opened_on": "2021-04-01"}  # 초옹장 (s005) 시험용 값
PEOPLES = {"business_no": "4128705567", "owner_name": "김 도나", "opened_on": "2019-09-02"}  # 피플스클럽 (s004)
PLACES = {"s004": "1909851296", "s005": "2004174048"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(registered_stores, "REGISTRY_PATH", tmp_path / "registry.db")
    monkeypatch.setattr(registered_stores, "place_info", lambda sid: SimpleNamespace(place_id=PLACES[sid]) if sid in PLACES else None)
    monkeypatch.setattr(owner_router, "list_store_ids", lambda: ["s001", "s004", "s005"])
    monkeypatch.setattr(review, "REVIEW_SECONDS", 0)
    return TestClient(create_app())


def _check(client, owner_key="naver:demo", store_id="s005", document="등록증.jpg", **values) -> dict:
    body = {"store_id": store_id, "owner_key": owner_key, "document": document, **CHOONG, **values}
    res = client.post("/api/owner_check", json=body)
    assert res.status_code == 200, res.json()
    return client.get(f"/api/owner_check/{res.json()['check_id']}").json()


def test_sample_values_pass_and_link_account_to_store(client):
    assert registered_stores.store_for_owner("naver:demo") is None
    result = _check(client)
    assert result["status"] == "approved" and result["reason_code"] is None
    assert result["business_no"] == "120-81-*****"  # 번호는 가려서 보낸다
    assert registered_stores.store_for_owner("naver:demo") == "s005"  # 승인되면 계정과 가게를 잇는다
    assert _check(client, store_id="s004", **PEOPLES)["status"] == "approved"  # 띄어쓰기는 무시


def test_review_waits_before_result(client, monkeypatch):
    monkeypatch.setattr(review, "REVIEW_SECONDS", 60)
    first = client.post("/api/owner_check", json={"store_id": "s005", "owner_key": "naver:demo", "document": "a.jpg", **CHOONG}).json()
    assert first["status"] == "reviewing" and first["seconds_left"] > 50
    assert client.get(f"/api/owner_check/{first['check_id']}").json()["status"] == "reviewing"
    assert registered_stores.store_for_owner("naver:demo") is None  # 심사 중에는 잇지 않는다


@pytest.mark.parametrize(
    ("values", "code"),
    [
        ({"business_no": "1208103451"}, "INVALID_BUSINESS_NO"),  # 검증 숫자가 틀림
        ({"business_no": "12081034"}, "INVALID_BUSINESS_NO"),
        ({"owner_name": " "}, "OWNER_NAME_REQUIRED"),
        ({"opened_on": "2021-13-01"}, "INVALID_OPENED_ON"),
        ({"opened_on": "2999-01-01"}, "INVALID_OPENED_ON"),
        ({"document": None}, "DOCUMENT_REQUIRED"),
    ],
)
def test_wrong_input_is_refused_before_review(client, values, code):
    body = {"store_id": "s005", "owner_key": "naver:demo", "document": "a.jpg", **CHOONG, **values}
    res = client.post("/api/owner_check", json=body)
    assert res.status_code == 422 and res.json()["error"]["code"] == code


@pytest.mark.parametrize(
    ("values", "store_id", "code"),
    [
        ({"business_no": "5081207344"}, "s005", "NTS_NOT_FOUND"),  # 모양은 맞지만 국세청에 없음
        ({"owner_name": "이도나"}, "s005", "NTS_MISMATCH"),
        ({"opened_on": "2021-04-02"}, "s005", "NTS_MISMATCH"),
        ({"business_no": "2159301277", "opened_on": "2015-05-20"}, "s005", "CLOSED"),
        ({"business_no": "3164509829", "opened_on": "2018-03-12"}, "s005", "SUSPENDED"),
        (PEOPLES, "s005", "OTHER_STORE"),  # 피플스클럽 사업자로 초옹장을 고름
        ({}, "s001", "OTHER_STORE"),  # 네이버 가게가 없는 목업 가게
    ],
)
def test_review_holds_with_reason(client, values, store_id, code):
    result = _check(client, store_id=store_id, **values)
    assert result["status"] == "held" and result["reason_code"] == code
    assert result["reason_title"] == review.REASONS[code][0]
    assert registered_stores.store_for_owner("naver:demo") is None


def test_store_confirmed_by_another_owner_is_held_until_they_withdraw(client):
    assert _check(client, owner_key="naver:first")["status"] == "approved"
    assert _check(client, owner_key="naver:second")["reason_code"] == "TAKEN"
    assert _check(client, owner_key="naver:first")["status"] == "approved"  # 같은 계정은 다시 해도 된다
    assert review.withdraw("naver:first") == 2
    assert _check(client, owner_key="naver:second")["status"] == "approved"


def test_sample_endpoint_gives_values_that_pass(client):
    body = client.get("/api/owner_check/sample", params={"store_id": "s005"}).json()
    assert body["trade_name"] == "초옹장" and body["document"]
    assert _check(client, business_no=body["business_no"], owner_name=body["owner_name"], opened_on=body["opened_on"])["status"] == "approved"
    assert client.get("/api/owner_check/sample", params={"store_id": "s001"}).json()["error"]["code"] == "NO_SAMPLE"


def test_unknown_store_and_check_are_refused(client):
    assert client.post("/api/owner_check", json={"store_id": "s999", "owner_key": "k", **CHOONG}).status_code == 404
    assert client.get("/api/owner_check/oc_nope").json()["error"]["code"] == "CHECK_NOT_FOUND"


def test_mock_numbers_follow_checksum_rule():
    for row in mock_nts.samples():
        assert mock_nts.is_valid_number(row["business_no"]), row
    assert mock_nts.digits("120-81-03450") == "1208103450"
