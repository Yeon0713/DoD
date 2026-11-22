"""H: 사장님이 말로 알바생 일을 시키기 (2026-11-18, voice/staff_orders.py). 회의 결정은 donna-voice/docs/operating-scenarios.md 2-3장.

H1  "하린이한테 … 넣으라고 해" → 읽어 주고 묻기 → "응" → 하린 할 일 화면에 "방금"으로, 자세히 보면 사장님 말 그대로 (D-17, F-08)
H2  "오늘은 장칼국수 주문 받지 말라고 해" → 하지 말 것, 오늘 나온 사람 모두 (D-20)
H3  "시킨 거 다 했대?" → 한 것과 안 한 것 (D-24)
H4  "그거 취소해" → 알바생 화면에서 사라짐. 이미 했으면 취소하지 않음 (D-33)
H5  초대: 랜덤 6자리, 다시 초대하면 예전 코드는 못 씀, 카카오톡으로 보내면 시연 메신저에 도착 (D-04, F-01)
H6  내보내기: 코드와 로그인 표시가 끊김
H7  없는 이름, 안 들어온 사람
H8  "알바생 누구 있어?", "오늘 누구 나왔어?" (D-30), "매뉴얼 보여 줘" (D-06)
"""

import re

from voice.staff_orders import parse_order
from voice.tests.conftest import choongjang

AT = "2026-11-17T15:35:00+09:00"


def all_titles(today: dict) -> list[str]:
    return [t["title"] for g in today["groups"] for t in g["must"] + g["tasks"]] + [t["title"] for t in today.get("urgent", [])]


# ── 말에서 뽑기 ──


def test_parse_order_takes_recipient_title_and_kind():
    order = parse_order("하린이한테 오늘 들어온 감자가 물이 많으니까 감자전 반죽에 전분 한 숟갈 더 넣으라고 해")
    assert (order["who"], order["name"], order["title"], order["kind"], order["repeat"]) == (
        "name", "하린", "감자전 반죽에 전분 한 숟갈 더 넣기", "do", "today")
    dont = parse_order("새뱅이 다 떨어졌으니까 오늘은 장칼국수 주문 받지 말라고 해 줘")
    assert (dont["who"], dont["title"], dont["kind"]) == ("all", "장칼국수 주문 받지 않기", "dont")
    daily = parse_order("앞으로 마감 때 냉장고 온도 적으라고 매뉴얼에 넣어 줘")
    assert (daily["title"], daily["repeat"], daily["phase"]) == ("냉장고 온도 적기", "daily", "closing")
    must = parse_order("모두에게 메밀 알레르기 먼저 여쭤보라고 해")
    assert (must["who"], must["title"], must["must_confirm"]) == ("everyone", "메밀 알레르기 먼저 여쭤보기", True)
    guest = parse_order("손님한테 음료 하나 드리라고 해")
    assert (guest["who"], guest["title"]) == ("all", "손님한테 음료 하나 드리기")  # 손님은 받는 사람이 아니라 할 일의 일부다


# ── H1 시키기 ──


def test_h1_order_to_one_person_after_confirmation():
    donna = choongjang(at=AT)
    asked = donna.turn("하린이한테 오늘 들어온 감자가 물이 많으니까 감자전 반죽에 전분 한 숟갈 더 넣으라고 해", addressed=True)
    assert asked["intent"] == "staff.order" and asked["type"] == "ask" and asked["expects_reply"] is True
    assert asked["say"][0]["text"] == "하린 씨에게 '감자전 반죽에 전분 한 숟갈 더 넣기'를 보낼게요."
    assert "감자전 반죽에 전분 한 숟갈 더 넣기" not in all_titles(donna.staff_today())  # 묻는 동안에는 아직 안 간다
    sent = donna.turn("응, 보내 줘")
    assert sent["intent"] == "staff.yes" and sent["headline"] == "보냈어요"
    today = donna.staff_today()
    [task] = [t for g in today["groups"] for t in g["tasks"] if t["title"] == "감자전 반죽에 전분 한 숟갈 더 넣기"]
    assert task["fresh"] is True and task["sub"] == "오늘만" and task["has_words"] is True
    detail = donna.client.get(f"/v1/staff/tasks/{task['id']}", headers=donna.as_staff("st_harin")).json()
    assert detail["owner_words"].startswith("“하린이한테 오늘 들어온 감자가") and detail["owner_words_label"] == "사장님이 오후 3시 35분에 한 말"
    # 하린에게만 보낸 일은 다른 알바생 화면에 없다
    assert "감자전 반죽에 전분 한 숟갈 더 넣기" not in all_titles(donna.staff_today("st_yang"))


def test_h1_no_means_not_sent():
    donna = choongjang(at=AT)
    donna.turn("하린이한테 테이블 닦으라고 해", addressed=True)
    assert donna.turn("아니")["intent"] == "staff.no"
    assert "테이블 닦기" not in all_titles(donna.staff_today())


def test_h2_dont_goes_to_everyone_today_and_is_gone_tomorrow():
    donna = choongjang(at=AT)
    donna.turn("새뱅이 다 떨어졌으니까 오늘은 장칼국수 주문 받지 말라고 해 줘", addressed=True)
    donna.turn("응")
    assert "장칼국수 주문 받지 않기" in all_titles(donna.staff_today("st_yang"))
    donna.clock("2026-11-18T11:00:00+09:00")
    assert "장칼국수 주문 받지 않기" not in all_titles(donna.staff_today())


def test_h1_daily_goes_into_manual():
    donna = choongjang(at=AT)
    asked = donna.turn("앞으로 마감 때 분리배출 하라고 해", addressed=True)
    assert asked["headline"] == "매뉴얼에 넣을까요?"
    donna.turn("응")
    donna.clock("2026-11-19T11:00:00+09:00")
    closing = next(g for g in donna.staff_today()["groups"] if g["phase"] == "closing")
    assert "분리배출 하기" in [t["title"] for t in closing["tasks"]]


# ── H3 다 했대? ──


def test_h3_status_lists_left_and_done():
    donna = choongjang(at=AT)
    assert donna.turn("시킨 거 다 했대?", addressed=True)["headline"] == "오늘 시킨 일이 없어요"
    for line in ("하린이한테 테이블 닦으라고 해", "하린이한테 수저 채우라고 해"):
        donna.turn(line, addressed=True)
        donna.turn("응")
    task = next(t for g in donna.staff_today()["groups"] for t in g["tasks"] if t["title"] == "테이블 닦기")
    donna.clock("2026-11-17T15:40:00+09:00")
    donna.staff_post(f"/tasks/{task['id']}/done", staff_id="st_harin")
    answer = donna.turn("시킨 거 다 했대?", addressed=True)
    assert answer["intent"] == "staff.status" and answer["headline"] == "수저 채우기만 남았어요"
    items = {i["title"]: (i["state"], i["sub"]) for i in answer["cards"][0]["items"]}
    assert items == {"수저 채우기": ("todo", "하린 씨에게 보냄"), "테이블 닦기": ("done", "하린 씨가 오후 3시 40분에 함")}


# ── H4 취소 ──


def test_h4_cancel_removes_from_staff_screen():
    donna = choongjang(at=AT)
    donna.turn("하린이한테 감자전 반죽에 전분 더 넣으라고 해", addressed=True)
    donna.turn("응")
    assert "감자전 반죽에 전분 더 넣기" in all_titles(donna.staff_today())
    canceled = donna.turn("그거 취소해", addressed=True)
    assert canceled["intent"] == "staff.cancel" and canceled["headline"] == "취소했어요"
    assert canceled["cards"][0]["items"][0]["state"] == "canceled"
    assert "감자전 반죽에 전분 더 넣기" not in all_titles(donna.staff_today())


def test_h4_cancel_by_word_and_not_when_already_done():
    donna = choongjang(at=AT)
    for line in ("하린이한테 테이블 닦으라고 해", "하린이한테 수저 채우라고 해"):
        donna.turn(line, addressed=True)
        donna.turn("응")
    table = next(t for g in donna.staff_today()["groups"] for t in g["tasks"] if t["title"] == "테이블 닦기")
    donna.staff_post(f"/tasks/{table['id']}/done", staff_id="st_harin")
    kept = donna.turn("테이블 닦는 거 취소해", addressed=True)
    assert kept["headline"] == "벌써 했어요" and kept["say"][0]["text"] == "하린 씨가 벌써 했어요."
    assert "테이블 닦기" in all_titles(donna.staff_today())
    assert donna.turn("그거 취소해", addressed=True)["headline"] == "취소했어요"  # 방금 보낸 수저 채우기
    assert "수저 채우기" not in all_titles(donna.staff_today())


# ── H5 초대 ──


def invite(donna, line="하린이 초대해 줘") -> str:
    turn = donna.turn(line, addressed=True)
    assert turn["intent"] == "staff.invite" and turn["type"] == "ask", turn
    [card] = [c for c in turn["cards"] if c["type"] == "invite"]
    return card["code"].replace(" ", "")


def test_h5_invite_makes_random_six_digit_code():
    donna = choongjang(at=None)
    first = invite(donna)
    assert re.fullmatch(r"[1-9]\d{5}", first)
    second = invite(donna)  # 다시 초대하면 새 코드, 예전 코드는 못 쓴다
    assert second != first
    assert donna.staff_post("/invite/check", code=first).json()["ok"] is False
    assert donna.staff_post("/invite/check", code=second).json()["name"] == "하린"


def test_h5_share_puts_message_in_demo_messenger():
    donna = choongjang(at=None)
    code = invite(donna)
    assert donna.get("/v1/dev/messenger", to="하린")["items"] == []  # 보내기 전에는 없다
    shared = donna.turn("카카오톡으로 보내 줘")
    assert shared["intent"] == "staff.yes" and shared["open"] == "kakao_share"
    [message] = donna.get("/v1/dev/messenger", to="하린")["items"]
    assert message["link"] == f"/staff?code={code}" and message["url"] == "donna.app/s/choongjang"
    # 알바생: 링크 → 코드 → 가입 → 시작 → 사장님 알림 (F-02 ~ F-04, D-05)
    signed = donna.staff_post("/signup", code=code, name="하린", login_id="harin01", password="donna1234").json()
    donna.client.post("/v1/staff/start", headers={"X-Staff-Token": signed["token"]})
    assert [n["text"] for n in donna.notices()] == ["하린 씨가 알바생 화면에 들어왔어요"]


def test_h5_new_person_is_added_to_roster():
    donna = choongjang(at=None)
    code = invite(donna, "민지 초대해 줘")
    assert donna.staff_post("/invite/check", code=code).json()["name"] == "민지"


def test_h5_already_joined_person_is_not_invited():
    donna = choongjang(at=None)
    assert donna.turn("수아 초대해 줘", addressed=True)["headline"] == "수아 씨는 들어와 있어요"


# ── H6 내보내기 ──


def test_h6_remove_ends_login():
    donna = choongjang(at=AT)
    assert donna.client.get("/v1/staff/today", headers=donna.as_staff("st_harin")).status_code == 200
    asked = donna.turn("하린이 내보내 줘", addressed=True)
    assert asked["intent"] == "staff.remove" and asked["type"] == "ask"
    assert donna.turn("응")["headline"] == "내보냈어요"
    assert donna.client.get("/v1/staff/today", headers=donna.as_staff("st_harin")).status_code == 401
    assert donna.get("/v1/settings")["staff_count"] == 4


# ── H7 이름 ──


def test_h7_unknown_name_suggests_similar():
    donna = choongjang(at=AT)
    asked = donna.turn("하림이한테 테이블 닦으라고 해", addressed=True)
    assert asked["headline"] == "하림 씨는 없어요" and asked["say"][1]["text"] == "비슷한 이름은 하린 씨예요."
    confirm = donna.turn("응")
    assert confirm["say"][0]["text"] == "하린 씨에게 '테이블 닦기'를 보낼게요."
    donna.turn("응")
    assert "테이블 닦기" in all_titles(donna.staff_today())


def test_h7_not_joined_person_offers_invite():
    donna = choongjang(at=AT)
    asked = donna.turn("정우한테 테이블 닦으라고 해", addressed=True)
    assert asked["say"][0]["text"] == "정우 씨는 아직 알바생 화면에 안 들어왔어요."
    invited = donna.turn("응")
    assert [c["type"] for c in invited["cards"]] == ["invite"] and invited["headline"] == "정우 씨 초대 코드예요"


# ── H9 사장님 앱이 둘 열려 있을 때 ──


def test_h9_two_owner_apps_hearing_the_same_words_do_it_once():
    """시연 화면과 다른 탭에 사장님 앱이 둘 열려 있으면 개발자 모드의 말을 둘 다 듣는다. 할 일·초대 코드는 하나만 생겨야 한다."""
    donna = choongjang(at=AT)

    def both(text, addressed=False):
        answers = []
        for session_id in ("sess_app_a", "sess_app_b"):
            donna.session_id = session_id
            answers.append(donna.turn(text, addressed=addressed))
        return answers

    a, b = both("정우 초대해 줘", addressed=True)
    assert a["cards"][0]["code"] == b["cards"][0]["code"]
    both("카카오톡으로 보내 줘")
    assert len(donna.get("/v1/dev/messenger", to="정우")["items"]) == 1
    both("하린이한테 테이블 닦으라고 해", addressed=True)
    both("응")
    assert all_titles(donna.staff_today()).count("테이블 닦기") == 1
    both("하린이한테 수저 채우라고 해", addressed=True)
    both("응")
    both("그거 취소해", addressed=True)
    titles = all_titles(donna.staff_today())
    assert "수저 채우기" not in titles and "테이블 닦기" in titles  # 두 번 취소되어 테이블 닦기까지 지워지지 않는다


# ── H8 목록, 매뉴얼 ──


def test_h8_list_and_present_today():
    donna = choongjang(at=AT)
    listed = donna.turn("알바생 누구 있어?", addressed=True)
    assert listed["intent"] == "staff.list" and listed["headline"] == "알바생 5명이에요"
    subs = {p["name"]: p["sub"] for p in listed["cards"][0]["items"]}
    assert subs["문하린"] == "오후 3시 35분에 들어옴" and subs["양지성"] == "오늘 아직 안 나옴" and subs["정우"] == "아직 초대 안 함"
    present = donna.turn("오늘 누구 나왔어?", addressed=True)
    assert present["headline"] == "오늘 한 명 나왔어요" and [p["name"] for p in present["cards"][0]["items"]] == ["문하린"]


def test_h8_manual_is_the_store_wide_three_groups():
    donna = choongjang(at=None)
    shown = donna.turn("알바생 매뉴얼 보여 줘", addressed=True)
    assert shown["intent"] == "staff.manual"
    assert [(g["label"], g["text"]) for g in shown["cards"][0]["groups"]] == [
        ("영업 준비", "바닥과 테이블 청소, 수저·냅킨 채우기"),
        ("영업 중", "빈 테이블 정리, 품절 메뉴 안내"),
        ("마감", "바닥 청소, 냉장고 온도 적기"),
    ]


# ── H10 오늘만인지 매일인지 (2026-11-18) ──


def test_h10_asks_today_or_daily_when_not_said():
    donna = choongjang(at=AT)
    asked = donna.turn("하린이한테 테이블 닦으라고 해", addressed=True)
    assert [s["text"] for s in asked["say"]] == ["하린 씨에게 '테이블 닦기'를 보낼게요.", "오늘만 할까요, 매일 할까요?"]
    assert donna.turn("오늘만")["intent"] == "staff.yes"
    assert next(t for g in donna.staff_today()["groups"] for t in g["tasks"] if t["title"] == "테이블 닦기")["sub"] == "오늘만"


def test_h10_daily_answer_goes_into_manual():
    donna = choongjang(at=AT)
    donna.turn("하린이한테 테이블 닦으라고 해", addressed=True)
    answered = donna.turn("매일")
    assert answered["intent"] == "staff.daily" and answered["headline"] == "매뉴얼에 넣었어요"
    assert next(t for g in donna.staff_today()["groups"] for t in g["tasks"] if t["title"] == "테이블 닦기")["sub"] == "매일"


def test_h10_said_today_is_a_simple_question():
    donna = choongjang(at=AT)
    asked = donna.turn("오늘은 하린이한테 테이블 닦으라고 해", addressed=True)
    assert [s["text"] for s in asked["say"]] == ["하린 씨에게 오늘 하루만 '테이블 닦기'를 보낼까요?"]


# ── H11 도나가 한 말이 마이크로 다시 들어옴 (2026-11-18) ──


def test_h11_donna_own_words_are_ignored():
    donna = choongjang(at=AT)
    asked = donna.turn("하린이한테 테이블 닦으라고 해", addressed=True)
    # 스피커에서 나온 도나 말을 받아 적은 것 (받아쓰기가 조금 다르게 적어도)
    heard_back = donna.turn("하린 씨에게 테이블 닦기를 보낼게요 오늘만 할까요 매일 할까요")
    assert heard_back["type"] == "ignore" and heard_back["intent"] == "echo"
    # 묻던 것은 그대로라 사장님의 "오늘만"은 처리된다
    assert donna.turn("오늘만")["headline"] == "보냈어요"
    assert all_titles(donna.staff_today()).count("테이블 닦기") == 1


def test_h11_app_lines_and_briefing_echo_are_ignored():
    donna = choongjang(at=AT)
    donna.turn("오늘 일정 브리핑해 줘", addressed=True)
    assert donna.turn("오늘은 오후 2시부터 비 소식이 있습니다")["intent"] == "echo"  # 브리핑 첫 요약 줄 (H-02)
    assert donna.turn("지금은 답하기 어려워요 조금 뒤에 다시 말씀해 주세요")["intent"] == "echo"


def test_h11_owner_commands_are_not_mistaken_for_echo():
    donna = choongjang(at=AT)
    donna.turn("하린이한테 테이블 닦으라고 해", addressed=True)
    donna.turn("오늘만")
    assert donna.turn("시킨 거 다 했대?", addressed=True)["intent"] == "staff.status"  # 도나의 "시킨 건 다 했어요"와 비슷해도 짧다
    assert donna.turn("하린이한테 수저 채우라고 해", addressed=True)["intent"] == "staff.order"


def test_h11_partly_misheard_echo_is_ignored_but_answers_are_not():
    donna = choongjang(at=AT)
    donna.turn("오늘 일정 브리핑해 줘", addressed=True)
    assert donna.turn("오늘은 오후 2시부터 피 소식이 있습니다")["intent"] == "echo"  # 받아쓰기가 '비'를 '피'로
    donna.turn("정우 초대해 줘", addressed=True)  # 도나: "… 카카오톡으로 보낼까요?"
    assert donna.turn("카카오톡으로 보내 줘")["intent"] == "staff.yes"  # 도나 말과 겹쳐도 대답이다


def test_h11_instagram_answers_are_not_echo():
    from voice.dialog import echo

    echo.forget("t_echo")
    echo.remember("t_echo", ["인스타그램에 올릴까요?"])
    assert echo.is_echo("t_echo", "인스타그램에 올릴까요")  # 도나 말은 거른다
    assert not echo.is_echo("t_echo", "인스타그램에 올리지 마")  # 사장님 대답은 도나 말과 겹쳐도 거르지 않는다
    assert not echo.is_echo("t_echo", "인스타그램에 올려 줘")
    echo.forget("t_echo")
