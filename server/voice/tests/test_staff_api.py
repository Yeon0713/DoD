"""S: 알바생 화면 (donna-voice/docs/test-scenarios-closed-loop.md S). 옛 목업에만 있던 /v1/staff/* 를 실제 백엔드로 옮긴 것."""

import pytest
from fastapi.testclient import TestClient

from voice import staff
from voice.tests.conftest import choongjang


def approved(donna):
    """15:40 국물 샘 리뷰 → 15:41 '응, 진행해' (L4 까지)."""
    donna.clock("2026-11-17T15:40:00+09:00")
    donna.demo_review("leak")
    donna.open_notice()
    donna.clock("2026-11-17T15:41:00+09:00")
    assert donna.turn("응, 진행해")["intent"] == "action.approve"


def invite_code(donna, name: str = "하린") -> str:
    """사장님이 말로 초대해 코드를 받는다 (D-04). 랜덤 6자리."""
    turn = donna.turn(f"{name}이 초대해 줘" if name == "하린" else f"{name} 초대해 줘", addressed=True)
    [card] = [c for c in turn["cards"] if c["type"] == "invite"]
    return card["code"].replace(" ", "")


def test_s1_invite_code():
    donna = choongjang(at=None)
    code = invite_code(donna)
    ok = donna.staff_post("/invite/check", code=code).json()
    assert ok["ok"] is True and ok["staff_id"] == "st_harin" and ok["name"] == "하린" and ok["store"]["name"] == "초옹장"
    bad = donna.staff_post("/invite/check", code="000000").json()
    assert bad == {"ok": False, "message": "코드가 맞지 않아요. 사장님에게 받은 코드를 확인해 주세요."}
    assert donna.staff_post("/invite/check", code="482017").json()["ok"] is False  # 예전 고정 코드는 이제 없다


def test_s2_join_notice():
    donna = choongjang(at=None)
    code = invite_code(donna, "정우")
    signed = donna.staff_post("/signup", code=code, name="정우", login_id="jungwoo", password="donna1234").json()
    assert signed["staff_id"] == "st_jungwoo" and signed["token"]
    headers = {"X-Staff-Token": signed["token"]}
    assert donna.client.post("/v1/staff/start", headers=headers).json() == {"ok": True}
    assert [(n["kind"], n["text"]) for n in donna.notices()] == [("staff_joined", "정우 씨가 알바생 화면에 들어왔어요")]
    donna.client.post("/v1/staff/start", headers=headers)
    assert donna.notices() == []  # 두 번 눌러도 한 번만


def test_s3_today_is_attendance_and_manual():
    donna = choongjang()
    today = donna.staff_today()
    assert today["attendance"] == {"state": "in", "label": "출근", "detail": "오후 3시 35분에 왔어요"}
    assert [g["phase"] for g in today["groups"]] == ["before_open", "open", "closing"]
    assert [g["now"] for g in today["groups"]] == [False, True, False] and today["now_after"] == "before_open"
    assert [t["title"] for t in today["groups"][2]["tasks"]] == ["바닥 청소", "냉장고 온도 적기"]
    assert today["urgent"] == []


def must(today: dict) -> list[dict]:
    return [t for g in today["groups"] for t in g["must"]]


def test_s4_fix_card_must_confirm():
    """교정 카드는 긴급이 아니라 영업 중 묶음의 '확인 필요'에 뜬다 (2026-11-20)."""
    donna = choongjang()
    approved(donna)
    today = donna.staff_today()
    assert today["urgent"] == []
    [card] = must(today)
    assert card["title"] == "배달 용기 이중 실링" and card["urgent"] is False and card["confirmed"] is False
    assert card["sub"] == "리뷰에서 나온 일" and card["fresh"] is True
    assert card["detail"] == "국물 메뉴는 랩을 두 번 씌우고 뚜껑에 테이프를 한 번 더 붙여 주세요"  # 화면에서 무엇을 할지 보인다
    assert next(g for g in today["groups"] if card in g["must"])["phase"] == "open"


def test_s5_detail():
    donna = choongjang()
    approved(donna)
    card = must(donna.staff_today())[0]
    detail = donna.client.get(f"/v1/staff/tasks/{card['id']}", headers=donna.as_staff("st_harin")).json()
    assert detail["owner_words"] == "국물 메뉴는 랩을 두 번 씌우고 뚜껑에 테이프를 한 번 더 붙여 주세요"
    assert detail["owner_words_label"] == "도나가 리뷰를 보고 넣은 일" and detail["tag"] == "확인 필요"
    assert detail["until"] == "내일까지 보여요"


def test_s6_fix_card_does_not_block_checkout_but_urgent_does():
    donna = choongjang()
    approved(donna)
    assert donna.staff_post("/checkout", staff_id="st_harin").json() == {"ok": True}  # 교정 카드는 퇴근을 막지 않는다
    staff.add_task("s005", "[이벤트] 스토리 태그 손님 음료 1캔 드리기", "open", urgent=True, origin="story_event")
    blocked = donna.staff_post("/checkout", staff_id="st_harin")
    assert blocked.status_code == 409
    assert blocked.json() == {"error": {"code": "urgent_unconfirmed", "message": "[이벤트] 스토리 태그 손님 음료 1캔 드리기를 먼저 확인해 주세요."}}


def test_s7_confirm_and_next_day():
    donna = choongjang()
    approved(donna)
    card = must(donna.staff_today())[0]
    donna.clock("2026-11-17T15:43:00+09:00")
    assert donna.staff_post(f"/tasks/{card['id']}/confirm", staff_id="st_harin").json() == {"ok": True}
    today = donna.staff_today()
    assert must(today) == []
    moved = next(t for g in today["groups"] for t in g["tasks"] if t["id"] == card["id"])
    assert moved["sub"] == "오후 3시 43분에 확인함" and moved["done"] is True
    # 확인 안 한 다른 알바생은 다음 날에도 '확인 필요'에 보인다 (넣은 날과 다음 날)
    donna.clock("2026-11-18T11:00:00+09:00")
    assert [t["title"] for t in must(donna.staff_today("st_yang"))] == ["배달 용기 이중 실링"]
    donna.clock("2026-11-19T11:00:00+09:00")
    assert must(donna.staff_today("st_yang")) == []


def test_s8_add_task_needs_origin():
    with pytest.raises(ValueError):
        staff.add_task("s005", "출처 없는 일", "open")


def test_s8_done_persists():
    donna = choongjang()
    task = donna.staff_today()["groups"][2]["tasks"][1]
    donna.staff_post(f"/tasks/{task['id']}/done", staff_id="st_harin")
    from voice.main import create_app

    again = TestClient(create_app())  # 앱을 새로 만들어도 저장소에 남아 있다 (로그인 표시도)
    today = again.get("/v1/staff/today", headers=donna.as_staff("st_harin")).json()
    marked = next(t for t in today["groups"][2]["tasks"] if t["id"] == task["id"])
    assert marked["done"] is True and marked["sub"] == "오후 3시 35분에 함"
    again.post(f"/v1/staff/tasks/{task['id']}/done", json={"undo": True}, headers=donna.as_staff("st_harin"))
    assert next(t for t in donna.staff_today()["groups"][2]["tasks"] if t["id"] == task["id"])["done"] is False
    # 매뉴얼은 날마다 새로: 다음 날에는 안 한 것으로 보인다
    donna.staff_post(f"/tasks/{task['id']}/done", staff_id="st_harin")
    donna.clock("2026-11-18T11:00:00+09:00")
    assert next(t for t in donna.staff_today()["groups"][2]["tasks"] if t["id"] == task["id"])["done"] is False


def test_s9_staff_count():
    donna = choongjang(at=None)
    assert donna.get("/v1/settings")["staff_count"] == 4  # 들어온 사람 넷 (하린과 정우는 아직)
    donna.join("하린")
    assert donna.get("/v1/settings")["staff_count"] == 5


# ── 로그인 (2026-11-18) ──


def test_s10_signup_rules_and_login():
    donna = choongjang(at=None)
    code = invite_code(donna)
    short = donna.staff_post("/signup", code=code, name="하린", login_id="harin01", password="1234")
    assert short.status_code == 400 and short.json()["error"]["code"] == "password_short"
    signed = donna.staff_post("/signup", code=code, name="하린", login_id="harin01", password="donna1234").json()
    assert signed["call"] == "하린" and signed["token"]
    again = donna.staff_post("/signup", code=code, name="하린", login_id="harin02", password="donna1234")
    assert again.json()["error"]["code"] == "code_used"  # 코드는 한 번만
    # 다른 기기: 아이디와 비밀번호로 다시 들어온다
    bad = donna.staff_post("/login", login_id="harin01", password="wrong-pass")
    assert bad.status_code == 401 and bad.json()["error"]["message"] == "아이디나 비밀번호가 맞지 않아요."
    logged = donna.staff_post("/login", login_id="HARIN01", password="donna1234").json()
    assert logged["staff_id"] == "st_harin" and logged["token"] != signed["token"]
    assert donna.client.get("/v1/staff/today", headers={"X-Staff-Token": logged["token"]}).json()["staff"]["call"] == "하린"


def test_s11_login_id_must_be_unique():
    donna = choongjang(at=None)
    donna.staff_post("/signup", code=invite_code(donna), name="하린", login_id="sameid", password="donna1234")
    taken = donna.staff_post("/signup", code=invite_code(donna, "정우"), name="정우", login_id="SameId", password="donna1234")
    assert taken.status_code == 409 and taken.json()["error"]["message"] == "이미 쓰는 아이디예요. 다른 아이디를 정해 주세요."


def test_s12_token_is_required():
    donna = choongjang()
    assert donna.client.get("/v1/staff/today").status_code == 401
    assert donna.client.get("/v1/staff/today", params={"staff_id": "st_harin"}).status_code == 401  # 번호만으로는 못 연다
    assert donna.client.get("/v1/staff/today", headers={"X-Staff-Token": "made-up"}).json()["error"]["code"] == "not_signed_in"


def test_s13_password_is_not_stored_as_is():
    from voice import staff_db

    donna = choongjang(at=None)
    donna.staff_post("/signup", code=invite_code(donna), name="하린", login_id="harin01", password="donna1234")
    stored = staff_db.member("st_harin")["password_hash"]
    assert "donna1234" not in stored and stored.startswith("pbkdf2$")
