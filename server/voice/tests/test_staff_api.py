"""S: 알바생 화면 (donna-voice/docs/test-scenarios-closed-loop.md S). 옛 목업에만 있던 /v1/staff/* 를 실제 백엔드로 옮긴 것."""

from fastapi.testclient import TestClient

from voice.tests.conftest import choongjang


def approved(donna):
    """15:40 국물 샘 리뷰 → 15:41 '응, 진행해' (L4 까지)."""
    donna.clock("2026-11-17T15:40:00+09:00")
    donna.demo_review("leak")
    donna.open_notice()
    donna.clock("2026-11-17T15:41:00+09:00")
    assert donna.turn("응, 진행해")["intent"] == "action.approve"


def test_s1_invite_code():
    donna = choongjang(at=None)
    ok = donna.staff_post("/invite/check", code="482017").json()
    assert ok["ok"] is True and ok["staff_id"] == "st_harin" and ok["name"] == "하린" and ok["store"]["name"] == "초옹장"
    bad = donna.staff_post("/invite/check", code="000000").json()
    assert bad == {"ok": False, "message": "코드가 맞지 않아요. 사장님에게 받은 코드를 확인해 주세요."}


def test_s2_join_notice():
    donna = choongjang(at=None)
    signed = donna.staff_post("/signup", code="315904", name="정우", login_id="jungwoo", password="x").json()
    assert signed["staff_id"] == "st_jungwoo"
    assert donna.staff_post("/start", staff_id="st_jungwoo").json() == {"ok": True}
    assert [(n["kind"], n["text"]) for n in donna.notices()] == [("staff_joined", "정우 씨가 알바생 화면에 들어왔어요")]
    donna.staff_post("/start", staff_id="st_jungwoo")
    assert donna.notices() == []  # 두 번 눌러도 한 번만


def test_s3_today_is_attendance_and_manual():
    donna = choongjang()
    today = donna.staff_today()
    assert today["attendance"] == {"state": "in", "label": "출근", "detail": "오후 3시 35분에 왔어요"}
    assert [g["phase"] for g in today["groups"]] == ["before_open", "open", "closing"]
    assert [g["now"] for g in today["groups"]] == [False, True, False] and today["now_after"] == "before_open"
    assert [t["title"] for t in today["groups"][2]["tasks"]] == ["바닥 청소", "냉장고 온도 적기"]
    assert today["urgent"] == []


def test_s4_urgent_pinned():
    donna = choongjang()
    approved(donna)
    today = donna.staff_today()
    [card] = today["urgent"]
    assert card["title"] == "배달 용기 이중 실링" and card["urgent"] is True and card["confirmed"] is False
    assert card["sub"] == "리뷰에서 나온 일" and card["fresh"] is True
    assert card["id"] not in [t["id"] for g in today["groups"] for t in g["must"] + g["tasks"]]  # 맨 위에만 한 번


def test_s5_detail():
    donna = choongjang()
    approved(donna)
    card = donna.staff_today()["urgent"][0]
    detail = donna.client.get(f"/v1/staff/tasks/{card['id']}", params={"staff_id": "st_harin"}).json()
    assert detail["owner_words"] == "국물 메뉴는 랩을 두 번 씌우고 뚜껑에 테이프를 한 번 더 붙여 주세요"
    assert detail["owner_words_label"] == "도나가 리뷰를 보고 넣은 일" and detail["tag"] == "긴급"


def test_s6_checkout_blocked_until_confirmed():
    donna = choongjang()
    approved(donna)
    blocked = donna.staff_post("/checkout", staff_id="st_harin")
    assert blocked.status_code == 409
    assert blocked.json() == {"error": {"code": "urgent_unconfirmed", "message": "배달 용기 이중 실링을 먼저 확인해 주세요."}}


def test_s7_checkout_after_confirm():
    donna = choongjang()
    approved(donna)
    card = donna.staff_today()["urgent"][0]
    donna.clock("2026-11-17T15:43:00+09:00")
    assert donna.staff_post(f"/tasks/{card['id']}/confirm", staff_id="st_harin").json() == {"ok": True}
    today = donna.staff_today()
    assert today["urgent"] == []
    moved = next(t for g in today["groups"] for t in g["tasks"] if t["id"] == card["id"])
    assert moved["sub"] == "오후 3시 43분에 확인함" and moved["done"] is True
    assert donna.staff_post("/checkout", staff_id="st_harin").json() == {"ok": True}
    assert donna.staff_today()["attendance"]["label"] == "퇴근"
    # 확인 안 한 다른 알바생은 다음 날에도 맨 위에 보인다 (넣은 날과 다음 날)
    donna.clock("2026-11-18T11:00:00+09:00")
    assert [t["title"] for t in donna.staff_today("st_yang")["urgent"]] == ["배달 용기 이중 실링"]
    donna.clock("2026-11-19T11:00:00+09:00")
    assert donna.staff_today("st_yang")["urgent"] == []


def test_s8_done_persists():
    donna = choongjang()
    task = donna.staff_today()["groups"][2]["tasks"][1]
    donna.staff_post(f"/tasks/{task['id']}/done", staff_id="st_harin")
    from voice.main import create_app

    again = TestClient(create_app())  # 앱을 새로 만들어도 저장소에 남아 있다
    today = again.get("/v1/staff/today", params={"staff_id": "st_harin"}).json()
    marked = next(t for t in today["groups"][2]["tasks"] if t["id"] == task["id"])
    assert marked["done"] is True and marked["sub"] == "오후 3시 35분에 함"
    again.post(f"/v1/staff/tasks/{task['id']}/done", json={"staff_id": "st_harin", "undo": True})
    assert next(t for t in donna.staff_today()["groups"][2]["tasks"] if t["id"] == task["id"])["done"] is False
    # 매뉴얼은 날마다 새로: 다음 날에는 안 한 것으로 보인다
    donna.staff_post(f"/tasks/{task['id']}/done", staff_id="st_harin")
    donna.clock("2026-11-18T11:00:00+09:00")
    assert next(t for t in donna.staff_today()["groups"][2]["tasks"] if t["id"] == task["id"])["done"] is False


def test_s9_staff_count():
    donna = choongjang(at=None)
    assert donna.get("/v1/settings")["staff_count"] == 5  # 들어온 사람 다섯 (정우는 아직)
