"""L·E·T·G: 아쉬운 리뷰 → 알림 → 사장님 한마디 → 답글 + 알바생 교정 카드 → 알바생 확인 (닫힌 고리).

번호는 donna-voice/docs/test-scenarios-closed-loop.md 와 같다. 에이전트는 꺼져 있어 답글은 원인별 템플릿이다.
공통 준비: 초옹장 11/17, 부정 리뷰 답글 인턴(묻기), 15:35 하린 출근, 15:40 국물 샘 리뷰.
부정 리뷰 답글 대리(묻지 않고 올림 → 할 일은 다음 날 브리핑)는 A 묶음 (2026-11-20, 2026-11-21 인사과 4-a).
"""

import re

import pytest

from voice import hr, repo, width
from voice.tests.conftest import Choongjang, choongjang, hr_log, step_key, walk_to

LEAK_PRESET = "다음 주문 때 감자전 하나를 서비스로 드릴게요."
MISSING_PRESET = "빠진 메뉴는 다음 주문 때 함께 챙겨 드릴게요."


def leak(permission=None) -> tuple[Choongjang, str]:
    donna = choongjang(permission=permission)
    donna.clock("2026-11-17T15:40:00+09:00")
    return donna, donna.demo_review("leak")


def alert_of(review_id: str) -> dict:
    return repo.get("alert", f"al_{review_id}")


def review(review_id: str) -> dict:
    return repo.review(review_id)


def fix_cards(donna: Choongjang, staff_id: str = "st_harin") -> list[dict]:
    """아쉬운 리뷰에서 나온 교정 카드. 긴급이 아니라 '확인 필요'에 뜬다 (2026-11-20)."""
    today = donna.staff_today(staff_id)
    assert today["urgent"] == []  # 맨 위 긴급에는 올라가지 않는다 (퇴근을 막지 않는다)
    return [t for g in today["groups"] for t in g["must"] if t["sub"] == "리뷰에서 나온 일"]


def jobs(donna: Choongjang, review_id: str) -> dict[str, str]:
    return {j["kind"]: j["due_at"][11:16] for j in donna.state()["job"] if j["payload"].get("review_id") == review_id}


# ── L 고리 ──


def test_l1_alert_created():
    donna, rid = leak()
    record = alert_of(rid)
    assert record["state"] == "alerted" and record["cause"] == {"type": "packaging", "detail": "leak", "summary": "국물이 샜대요"}
    assert review(rid)["reply_status"] == "proposed"
    assert jobs(donna, rid) == {"review_alert": "15:40", "review_remind": "15:55", "review_fallback": "16:05"}  # 바로 답하기(auto_reply) 없음


def test_l2_notice_once():
    donna, _ = leak()
    first = donna.notices()
    assert [(n["kind"], n["opens_turn"], n["text"]) for n in first] == [("negative_review", True, "배민에 아쉬운 리뷰가 올라왔어요")]
    assert donna.notices() == []


def test_l3_alert_turn():
    donna, rid = leak()
    asked = donna.open_notice()
    assert asked["type"] == "ask_action" and asked["expects_reply"] is True and asked["headline"] == "아쉬운 리뷰가 왔어요"
    assert [s["text"] for s in asked["say"]] == [
        "사장님, 방금 배민에 국물이 샜다는 아쉬운 리뷰가 올라왔어요.",
        "사과 답글에 다음 주문 서비스 안내를 넣어 올리고, 알바생 할 일에 배달 용기 이중 실링을 넣을까요?"]
    review_card, todo = asked["cards"]
    assert review_card["reply"]["text"].endswith(LEAK_PRESET) and review_card["reply"]["posted_at"] is None
    assert review_card["reply"]["text"].startswith("국물이 새서 불편하게 해 드려 정말 죄송합니다.")
    assert todo["type"] == "checklist" and todo["items"][0]["title"] == "배달 용기 이중 실링" and "tone" not in todo["items"][0]
    assert asked["action"] == {"kind": "review_fix", "alert_id": f"al_{rid}", "compensation": True, "staff_card": "배달 용기 이중 실링",
                               "deadline_at": "2026-11-17T16:10:00+09:00"}


def test_l4_approve():
    donna, rid = leak()
    donna.open_notice()
    donna.clock("2026-11-17T15:41:00+09:00")
    done = donna.turn("응, 진행해")
    assert done["intent"] == "action.approve" and done["type"] == "answer" and done["headline"] == "답글 올리고 할 일 넣었어요"
    assert [s["text"] for s in done["say"]] == ["서비스 안내를 넣어 사과 답글을 올렸어요.", "알바생 할 일에 배달 용기 이중 실링을 넣었어요.",
                                                "알바생이 확인하면 알려 드릴게요."]
    posted = review(rid)
    assert posted["reply_status"] == "posted" and posted["reply_trigger"] == "owner_yes" and posted["replied_in_minutes"] == 1
    assert posted["reply_text"].endswith(LEAK_PRESET) and posted["reply_posted_at"] == "2026-11-17T15:41:00+09:00"
    assert alert_of(rid)["state"] == "card_pinned"
    assert [t["title"] for t in fix_cards(donna)] == ["배달 용기 이중 실링"]
    assert hr_log() == [("negative_reply", "approved"), ("review_fix_task", "approved")]
    mine = [e for e in hr.events("s005") if not e["ref"].startswith("hist_")]  # 시나리오 파일의 지난 기록은 뺀다
    assert [e["said"] for e in mine] == ["응, 진행해"] * 2 and mine[0]["ref"] == rid


def test_l6_confirm_closes():
    donna, rid = leak()
    donna.open_notice()
    donna.clock("2026-11-17T15:41:00+09:00")
    donna.turn("응, 진행해")
    card = fix_cards(donna)[0]
    donna.clock("2026-11-17T15:43:00+09:00")
    donna.staff_post(f"/tasks/{card['id']}/confirm", staff_id="st_harin")
    assert alert_of(rid)["state"] == "closed"
    [notice] = donna.notices()
    assert notice["kind"] == "staff_checked" and notice["say"] == ["하린 씨가 배달 용기 이중 실링을 확인했어요."]
    # 다른 알바생이 확인해도 사장님 알림은 한 번만
    donna.staff_today("st_yang")
    donna.staff_post(f"/tasks/{card['id']}/confirm", staff_id="st_yang")
    assert donna.notices() == []


def test_l7_world_changed():
    donna, rid = leak()
    donna.open_notice()
    donna.clock("2026-11-17T15:41:00+09:00")
    donna.turn("응, 진행해")
    platform = donna.get("/v1/dev/platform")
    top = platform["items"][0]
    assert top["id"] == rid and top["platform_label"] == "배달 앱 리뷰" and top["menus"] == ["들깨옹심이메밀칼국수"]
    assert top["reply"]["posted_label"] == "오후 3시 41분" and top["reply"]["fresh"] is True and top["reply"]["text"].endswith(LEAK_PRESET)
    today = next(d for d in donna.get("/v1/week")["days"] if d["is_today"])
    assert {"아쉬운 리뷰에 사과 답글을 올렸어요", "알바생 할 일에 배달 용기 이중 실링을 넣었어요"} <= {d["text"] for d in today["done"]}


def test_l8_idempotent():
    donna, rid = leak()
    donna.open_notice()
    first = donna.turn("응, 진행해", request_id="req_yes")
    again = donna.turn("응, 진행해", request_id="req_yes")
    assert first == again and len(fix_cards(donna)) == 1
    assert len([a for a in repo.all_of("activity", "s005") if a["text"] == "아쉬운 리뷰에 사과 답글을 올렸어요"]) == 1


def test_l9_not_rereported():
    donna, rid = leak()
    donna.open_notice()
    donna.turn("응, 진행해")
    donna.clock("2026-11-18T10:00:00+09:00")  # 다음 날 브리핑은 09:30 에 준비된다
    donna.session_id = "sess_20261118_s005"
    started = donna.turn("오늘 일정 브리핑해 줘")
    assert started["briefing"] and started["briefing"]["step_key"] == "sum_reviews"
    steps = [started]  # 끝까지 듣는다 (사장님이 "응, 진행해"로 올린 답글은 H-10 에도 사후 보고에도 다시 나오지 않는다)
    while steps[-1]["type"] != "end":
        assert len(steps) < 20 and steps[-1]["briefing"]
        steps.append(donna.turn("응") if step_key(steps[-1]) == "detail_ask" else donna.turn(event="auto_next"))
    assert "negative_done" not in [step_key(s) for s in steps]
    assert all(rid not in [c.get("id") for c in s["cards"]] for s in steps)


# ── E 말로 고치기 ──


def test_e1_drop_compensation():
    donna, rid = leak()
    donna.open_notice()
    done = donna.turn("쿠폰 빼고 사과만 올려")
    assert done["intent"] == "action.approve" and done["say"][0]["text"] == "서비스 안내는 빼고 사과 답글을 올렸어요."
    assert LEAK_PRESET not in review(rid)["reply_text"] and review(rid)["reply_status"] == "posted"
    assert [t["title"] for t in fix_cards(donna)] == ["배달 용기 이중 실링"]
    assert hr_log() == [("negative_reply", "approved"), ("review_fix_task", "approved")]  # "쿠폰 빼고"도 답글은 그대로 승인 (9-0 k)


def test_e2_no_card():
    donna, rid = leak()
    donna.open_notice()
    edit = donna.turn("카드는 넣지 마")
    assert edit["intent"] == "action.edit" and edit["type"] == "ask_action" and edit["headline"] == "이렇게 올릴까요?"
    assert [s["text"] for s in edit["say"]] == ["알바생 할 일은 빼고, 사과 답글에 다음 주문 서비스 안내를 넣어 올릴까요?"]
    assert [c["type"] for c in edit["cards"]] == ["review"] and review(rid)["reply_status"] == "proposed"
    done = donna.turn("응, 올려")
    assert done["headline"] == "사과 답글을 올렸어요" and fix_cards(donna) == [] and alert_of(rid)["state"] == "closed"
    assert review(rid)["reply_text"].endswith(LEAK_PRESET)
    assert hr_log() == [("negative_reply", "approved"), ("review_fix_task", "rejected")]  # "카드는 넣지 마" (9-0 l)


def test_e3_edit_not_cancel():
    donna, rid = leak()
    donna.open_notice()
    edit = donna.turn("아니, 서비스는 빼")
    assert edit["intent"] == "action.edit" and alert_of(rid)["state"] == "alerted"
    assert edit["say"][0]["text"] == "서비스 안내는 빼고, 사과 답글을 올리고, 알바생 할 일에 배달 용기 이중 실링을 넣을까요?"
    done = donna.turn("진행해")
    assert done["intent"] == "action.approve" and LEAK_PRESET not in review(rid)["reply_text"] and len(fix_cards(donna)) == 1


def test_e4_cancel():
    donna, rid = leak()
    donna.open_notice()
    no = donna.turn("안 해")
    assert no["intent"] == "action.cancel" and [s["text"] for s in no["say"]] == ["네, 올리지 않을게요.", "초안은 남겨 둘게요."]
    assert review(rid)["reply_status"] == "drafted" and alert_of(rid)["state"] == "canceled"
    donna.clock("2026-11-17T16:10:00+09:00")
    assert review(rid)["reply_status"] == "drafted" and donna.notices() == [] and fix_cards(donna) == []
    assert hr_log() == [("negative_reply", "rejected"), ("review_fix_task", "rejected")]


def test_e5_two_edits():
    donna, rid = leak()
    donna.open_notice()
    done = donna.turn("사과만 올리고 카드도 빼")
    assert done["intent"] == "action.approve" and done["headline"] == "사과 답글을 올렸어요"
    assert LEAK_PRESET not in review(rid)["reply_text"] and fix_cards(donna) == []


def test_e6_no_preset():
    donna = choongjang(permission=None)
    donna.clock("2026-11-17T15:40:00+09:00")
    donna.demo_review("cold")
    asked = donna.open_notice()
    assert [s["text"] for s in asked["say"]] == [
        "사장님, 방금 배민에 국물이 식어서 왔다는 아쉬운 리뷰가 올라왔어요.",
        "사과 답글을 올리고, 알바생 할 일에 포장 직전 국물 데우기를 넣을까요?"]
    assert asked["action"]["compensation"] is False


def test_e7_missing():
    donna = choongjang(permission=None)
    donna.clock("2026-11-17T15:40:00+09:00")
    rid = donna.demo_review("missing")
    asked = donna.open_notice()
    assert alert_of(rid)["cause"]["type"] == "missing" and asked["cards"][0]["reply"]["text"].endswith(MISSING_PRESET)
    assert asked["cards"][1]["items"][0]["title"] == "봉투 닫기 전 주문서 대조"


# ── T 대답이 없을 때 ──


def test_t1_remind():
    donna, rid = leak()
    donna.notices()  # 알림 소리는 났지만 사장님이 열지 않음
    donna.clock("2026-11-17T15:55:00+09:00")
    assert alert_of(rid)["state"] == "reminded"
    asked = donna.open_notice()
    assert [s["text"] for s in asked["say"]] == ["사장님, 아까 그 국물 리뷰요.", "10분 안에 대답이 없으시면 답글은 초안으로 남겨 둘게요.",
                                                "서비스 안내와 할 일까지 넣어 올릴까요?"]


def test_t2_no_answer_leaves_draft():
    donna, rid = leak()
    donna.clock("2026-11-17T16:05:00+09:00")
    assert review(rid)["reply_status"] == "none" and alert_of(rid)["state"] == "left_draft" and fix_cards(donna) == []
    assert [(n["kind"], n["say"]) for n in donna.notices()] == [("reply_fallback", ["대답이 없으셔서 답글은 올리지 않고 초안으로 남겨 뒀어요."])]
    assert hr_log() == []  # 무응답은 세지 않는다


def test_t4_no_permission():
    donna, rid = leak(permission=None)
    donna.clock("2026-11-17T16:05:00+09:00")
    assert review(rid)["reply_status"] == "none" and alert_of(rid)["state"] == "left_draft"
    today = next(d for d in donna.get("/v1/week")["days"] if d["is_today"])
    assert "아쉬운 리뷰 3개에 답글 달기" in [r["text"] for r in today["remaining"]]  # 밤사이 2개 + 이 리뷰
    donna.clock("2026-11-18T10:00:00+09:00")
    donna.session_id = "sess_20261118_s005"
    # 다음 날 아침 리뷰 칸: 초안으로 남은 답글을 "올릴까요?"로 묻는다 (부정 리뷰 답글 인턴, 허락 질문은 없앰)
    asked = walk_to(donna, "negative")
    assert asked["type"] == "ask_action"
    assert asked["action"]["kind"] == "batch" and asked["action"]["mode"] == "each" and asked["say"][-1]["text"] == "써 둔 사과 답변을 올릴까요?"


def test_t6_clock_jump():
    donna, rid = leak()
    donna.clock("2026-11-17T17:00:00+09:00")
    assert [n["kind"] for n in donna.notices()] == ["reply_fallback"]
    assert alert_of(rid)["state"] == "left_draft"


def test_t7_after_hours():
    donna = choongjang(permission=True)  # 부정 리뷰 답글 대리: 문 닫은 뒤 리뷰에 묻지 않고 답한다
    donna.clock("2026-11-17T21:40:00+09:00")
    rid = donna.demo_review("leak")
    # 리뷰 알림은 없다 (21:00 인사과 보고 알림은 따로 온다, jobs/hr_night.py)
    assert alert_of(rid) is None and [n["kind"] for n in donna.notices()] in ([], ["hr_night"])
    donna.clock("2026-11-17T21:55:00+09:00")
    assert review(rid)["reply_status"] == "posted" and review(rid)["reply_posted_at"] == "2026-11-17T21:50:00+09:00"
    # 할 일은 바로 넣지 않고 다음 날 아침 브리핑에서 묻는다 (안 B). 답글은 같은 조치를 약속한다
    from voice import proposals

    found = proposals.for_review("s005", rid)
    assert found["state"] == "proposed" and found["ask_on"] == "2026-11-18" and found["payload"]["title"] == "배달 용기 이중 실링"
    assert "랩을 두 번" in review(rid)["reply_text"] and fix_cards(donna) == []


# ── G 안전장치 ──


def test_g1_nothing_without_yes():
    donna, rid = leak()
    donna.open_notice()
    donna.clock("2026-11-17T15:50:00+09:00")
    assert review(rid)["reply_status"] == "proposed" and fix_cards(donna) == []
    assert donna.get("/v1/dev/platform")["items"][0]["reply"] is None


def test_g2_kitchen_talk_ignored():
    donna, rid = leak()
    donna.open_notice()
    assert donna.turn("3번 테이블 치워 줘")["type"] == "ignore"
    assert donna.turn("네 손님 포장이세요?")["type"] == "ignore"
    assert review(rid)["reply_status"] == "proposed"
    assert donna.turn("응, 진행해")["intent"] == "action.approve" and review(rid)["reply_status"] == "posted"


def test_g4_bare_yes():
    donna, rid = leak()
    donna.open_notice()
    unclear = donna.turn("네")
    assert unclear["intent"] == "action.unclear" and unclear["type"] == "ask_action"
    assert unclear["say"][0]["text"] == "진행하시려면 '응, 진행해'라고 말씀해 주세요."
    assert review(rid)["reply_status"] == "proposed"
    assert donna.turn("네", addressed=True)["intent"] == "action.approve" and review(rid)["reply_status"] == "posted"


def test_g4_called_later_answers_the_open_question():
    """알림을 듣고 몇 분 뒤 "도나야, 진행해" (앱이 듣기 창을 닫은 뒤): 열려 있는 질문의 대답으로 본다."""
    donna, rid = leak()
    donna.open_notice()
    donna.session_id = "sess_other_app_load"
    assert donna.turn("진행해", addressed=True)["intent"] == "action.approve" and review(rid)["reply_status"] == "posted"


def test_g8_widths_and_no_rating_numbers():
    donna, rid = leak()
    responses = [donna.open_notice(), donna.turn("카드는 넣지 마"), donna.turn("응, 올려"), donna.turn("응")]
    for response in responses:
        assert width.violations(response) == [], (response["headline"], width.violations(response))
        spoken = " ".join(s["text"] for s in response["say"])
        assert not re.search(r"별\s?\d|\d\s?점|별점", spoken), spoken


def test_g9_double_yes():
    donna, rid = leak()
    donna.open_notice()
    donna.turn("응", request_id="req_a")
    again = donna.turn("응", request_id="req_b")
    assert again["headline"] == "답글은 이미 올렸어요" and again["say"][0]["text"] == "답글은 이미 올렸어요."
    assert len(fix_cards(donna)) == 1


@pytest.mark.parametrize("name, kind, card", [
    ("leak", "packaging", "배달 용기 이중 실링"), ("missing", "missing", "봉투 닫기 전 주문서 대조"),
    ("cold", "taste_temp", "포장 직전 국물 데우기"), ("hall", "hall_service", "손님이 부르면 먼저 대답하기")])
def test_four_cause_types(name, kind, card):
    donna = choongjang()
    donna.clock("2026-11-17T15:40:00+09:00")
    rid = donna.demo_review(name)
    record = alert_of(rid)
    assert record["cause"]["type"] == kind and record["card"]["title"] == card


def test_answer_goes_to_the_review_being_asked_now():
    """2026-11-18 브라우저 확인에서 찾음: 앞 리뷰가 대답 없음으로 처리된 뒤 새 리뷰 알림을 다른 기기(앱)가 열었을 때,
    이 기기에서 "쿠폰 빼고 사과만 올려"라고 하면 새 리뷰에 적용돼야 한다 (앞 리뷰에 카드를 넣으면 안 된다)."""
    donna, first = leak()
    donna.open_notice()  # 이 기기가 첫 리뷰 알림을 엶
    donna.clock("2026-11-17T16:05:00+09:00")  # 대답 없음 → 초안으로
    assert alert_of(first)["state"] == "left_draft"
    donna.notices()
    donna.clock("2026-11-17T16:10:00+09:00")
    second = donna.demo_review("leak")
    other = Choongjang()  # 다른 기기
    other.session_id = "sess_tablet"
    other.open_notice()
    done = donna.turn("쿠폰 빼고 사과만 올려", addressed=True)
    assert done["intent"] == "action.approve" and done["cards"][0]["id"] == second
    assert review(second)["reply_status"] == "posted" and LEAK_PRESET not in review(second)["reply_text"]
    assert alert_of(first)["state"] == "left_draft" and alert_of(first)["task_id"] is None


# ── A 부정 리뷰 답글 대리 (예전: 바로 답하기를 켠 가게) ──


def test_redo_does_not_post():
    """"다시 만들어 줘"(action.redo)를 승인으로 보고 답글을 올리고 할 일을 넣던 버그 (2026-11-21)."""
    donna, rid = leak()
    donna.open_notice()
    asked = donna.turn("다시 만들어 줘")
    assert asked["type"] == "ask_action" and review(rid)["reply_status"] == "proposed" and alert_of(rid)["state"] == "alerted"


def test_alert_does_not_go_through_a_team_lead(clova_on, monkeypatch):
    """팀장을 없앴다 (2026-11-21, agent-structure.md 5장). 다른 에이전트를 꺼 두면 알림까지 CLOVA 를 한 번도 부르지 않는다."""
    from Harness.tests.fakes import FakeClova
    from voice import config, proposals

    monkeypatch.setattr(config, "agent_on", lambda name: name == "lead")
    fake = clova_on(FakeClova())
    _, rid = leak()
    record = alert_of(rid)
    assert fake.requests == [] and record["use_card"] is True
    assert proposals.get(record["proposal_id"])["state"] == "asked"  # 팀장이 빼지 않고 그대로 묻는다


def test_a1_assistant_posts_without_asking_or_notice():
    """부정 리뷰 답글 대리 (예전: 바로 답하기를 켠 가게): 묻지 않고 올리고, 바로 알리지 않는다 (다음 날 아침 사후 보고, 인사과 4-a).
    교정 할 일은 알바생 할 일이라 늘 결재: 다음 아침 브리핑에서 묻는다."""
    from voice import proposals

    donna, rid = leak(permission=True)
    posted = review(rid)
    assert posted["reply_status"] == "posted" and posted["reply_trigger"] == "auto" and LEAK_PRESET not in posted["reply_text"]
    assert "랩을 두 번" in posted["reply_text"]  # 교정 카드와 같은 조치를 약속한다
    assert donna.notices() == [] and jobs(donna, rid) == {"review_alert": "15:40"}
    record = alert_of(rid)
    assert record["state"] == "carried" and fix_cards(donna) == []
    assert proposals.get(record["proposal_id"])["ask_on"] == "2026-11-18"
    assert hr_log() == [("negative_reply", "done")]  # 묻지 않고 처리한 것 (대리 → 과장 판정과 사후 보고에 쓴다)


def test_a2_no_answer_goes_to_next_morning():
    from voice import proposals

    donna, rid = leak(permission=True)
    donna.clock("2026-11-17T16:05:00+09:00")
    record = alert_of(rid)
    assert record["state"] == "carried" and fix_cards(donna) == []
    carried = proposals.get(record["proposal_id"])
    assert carried["state"] == "proposed" and carried["ask_on"] == "2026-11-18"
    donna.clock("2026-11-18T10:00:00+09:00")
    donna.session_id = "sess_20261118_s005"
    response = donna.turn("오늘 일정 브리핑해 줘")
    for _ in range(8):
        if response["type"] == "ask_tasks":
            break
        response = donna.turn("다음")
    assert response["type"] == "ask_tasks" and "배달 용기 이중 실링" in response["say"][-1]["text"]


def test_a4_late_delivery_makes_no_card():
    """배달 지연은 주문 기록이 생길 때까지 교정 카드를 만들지 않는다 (2026-11-20 결정)."""
    donna = choongjang(permission=None)
    donna.clock("2026-11-17T15:40:00+09:00")
    rid = donna.client.post("/v1/dev/reviews", json={"store_id": "s005", "platform": "baemin", "rating": 2,
                                                     "text": "배달이 한 시간 걸려서 다 식어서 왔어요."}).json()["review_id"]
    record = alert_of(rid)
    assert record["cause"]["detail"] == "late" and record["card"] is None and record["proposal_id"] is None


# ── 끝난 알림이 다른 질문의 대답을 가로채지 않는다 (2026-11-22 버그 V1) ──


def test_called_yes_to_another_question_is_not_a_review_answer():
    """반려한 알림이 2시간 안에 남아 있어도, 쉬는 날을 묻는 중의 "도나야, 응"은 그 질문의 대답이다."""
    from voice import holidays

    donna, rid = leak()
    donna.open_notice()
    donna.turn("안 해")
    donna.clock("2026-11-17T16:30:00+09:00")
    asked = donna.turn("다음 주 수요일 쉬어", addressed=True)
    assert asked["type"] == "ask_holiday"
    yes = donna.turn("응", addressed=True)
    assert yes["intent"] == "holiday.yes"
    assert review(rid)["reply_status"] == "drafted" and alert_of(rid)["state"] == "canceled"
    assert {"date": "2026-11-25", "confirmed": True}.items() <= holidays.items(repo.store("s005"))[0].items()


def test_called_yes_to_a_staff_question_is_not_a_review_answer():
    donna, rid = leak()
    donna.open_notice()
    donna.turn("안 해")
    donna.clock("2026-11-17T16:30:00+09:00")
    assert donna.turn("민지 초대해 줘", addressed=True)["type"] == "ask"
    yes = donna.turn("응", addressed=True)
    assert yes["intent"] == "staff.yes"
    assert review(rid)["reply_status"] == "drafted" and alert_of(rid)["state"] == "canceled"


def test_newer_alert_wins_over_old_unanswered_question():
    """한 시간 전 인스타 질문에 대답하지 않은 채 새 알림이 오면, "도나야, 진행해"는 나중에 온 알림의 대답이다 (2026-11-22 버그 V10)."""
    donna, rid = leak()
    repo.put("session", donna.session_id, "s005", {"id": donna.session_id, "store_id": "s005", "step": None, "mode": "idle",
                                                   "last_type": "ask", "last_at": "2026-11-17T14:40:00+09:00", "day": "2026-11-17"})
    approved = donna.turn("진행해", addressed=True)
    assert approved["intent"] == "action.approve" and review(rid)["reply_status"] == "posted"


# ── 끝난 알림의 할 일 제안을 정리한다 (2026-11-22 버그 V2) ──


def test_canceled_alert_does_not_swallow_the_next_fix_card():
    from voice import proposals

    donna, rid = leak()
    donna.open_notice()
    donna.turn("안 해")
    assert proposals.get(alert_of(rid)["proposal_id"])["state"] == "declined"
    donna.clock("2026-11-17T18:40:00+09:00")
    rid2 = donna.demo_review("leak")
    second = alert_of(rid2)
    assert second["card"] is not None and second["use_card"] is True
    assert proposals.get(second["proposal_id"])["state"] == "asked"
    assert "알바생 할 일에 배달 용기 이중 실링을" in donna.open_notice()["say"][-1]["text"]


def test_left_draft_proposal_is_closed():
    from voice import proposals

    donna, rid = leak()
    donna.clock("2026-11-17T16:06:00+09:00")
    assert alert_of(rid)["state"] == "left_draft"
    assert proposals.get(alert_of(rid)["proposal_id"])["state"] == "declined"


def test_fallback_posted_proposal_goes_to_next_morning():
    """25분 동안 대답이 없어 사과 답글만 올렸으면(알림 뒤 대리로 오름), 할 일은 다음 날 아침 브리핑에서 묻는다."""
    from voice import proposals

    donna, rid = leak()
    donna.settings(True)
    donna.clock("2026-11-17T16:06:00+09:00")
    assert alert_of(rid)["state"] == "fallback_posted"
    carried = proposals.get(alert_of(rid)["proposal_id"])
    assert carried["state"] == "proposed" and carried["ask_on"] == "2026-11-18"
    reopened = donna.turn("진행해", addressed=True)  # 그 뒤 "도나야, 진행해"면 카드만 넣는다 (지금처럼)
    assert reopened["headline"] == "알바생 할 일을 넣었어요" and len(fix_cards(donna)) == 1
    assert proposals.get(carried["id"])["state"] == "applied"


def test_reopen_after_cancel_still_pins_the_card():
    donna, rid = leak()
    donna.open_notice()
    donna.turn("안 해")
    donna.clock("2026-11-17T15:50:00+09:00")
    reopened = donna.turn("진행해", addressed=True)
    assert reopened["intent"] == "action.approve" and alert_of(rid)["state"] == "card_pinned"
    assert len(fix_cards(donna)) == 1
