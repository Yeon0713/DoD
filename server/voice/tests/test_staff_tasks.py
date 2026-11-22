"""알바생 할 일 묻기 (jobs/staff_tasks.py, 에이전트 조직 개편 3단계).

초옹장 11/17 아침: 밤사이 아쉬운 리뷰(면 불음, 옹심이 퍼짐)에서 같은 교정 카드 하나가 나와 브리핑 마지막에 묻는다.
12시 단체 예약 메모의 땅콩 알레르기도 규칙으로 할 일 제안이 된다 (agents/field_tasks.allergy_items, 2026-11-22).
교정 카드를 보는 시험은 알레르기 제안을 거절해 두고, 알레르기 제안은 H-11 · H-12 시험에서 따로 본다.
"""

from voice import clock, proposals, staff, width
from voice.jobs import briefing
from voice.tests.conftest import choongjang, hr_log, walk_to

SEAL = {"title": "배달 용기 이중 실링", "detail": "국물 메뉴는 랩을 두 번 씌우고 뚜껑에 테이프를 한 번 더 붙여 주세요",
        "phase": "open", "days": 2, "must_confirm": True, "urgent": False}
NOODLE = "배달 칼국수 면·국물 따로 담기"


def morning(keep: str = "negative_review"):
    """초옹장 11/17 09:02, keep 이 낸 할 일 제안만 그대로 둔 채 (negative_review: 리뷰 교정 카드, field_variable: 예약 메모 알레르기)."""
    donna = choongjang(keep_tasks=True, at=None)
    for found in proposals.for_briefing("s005", "2026-11-17"):
        if found["by"] != keep:
            proposals.decline(found["id"], "test")
    briefing.refresh_steps("s005")
    return donna


def to_tasks_step(donna) -> dict:
    response = walk_to(donna, "staff_tasks")
    assert response["type"] == "ask_tasks", "할 일 묻기 단계가 없어요"
    return response


def review_tasks() -> list[dict]:
    return [t for t in staff.store_tasks("s005") if t["origin"] == "review"]


def add_seal(review_id: str = "rv_x") -> dict:
    """오늘 물을 제안을 하나 더 둔다 (다른 리뷰, 다른 행동)."""
    return proposals.create("s005", dept="customer", by="negative_review", payload=SEAL, ask_on=clock.now().date().isoformat(),
                            reason={"type": "review", "review_id": review_id}, link={"type": "review", "review_id": review_id})


def test_morning_asks_and_yes_puts_it_in():
    donna = morning()
    asked = to_tasks_step(donna)
    assert asked["briefing"]["step_key"] == "staff_tasks" and asked["expects_reply"] is True
    done = donna.turn("응, 넣어")
    assert done["intent"] == "action.approve" and [s["text"] for s in done["say"]] == [
        f"알바생 할 일에 {NOODLE}를 넣었어요.", "알바생이 확인하면 알려 드릴게요."]
    [task] = review_tasks()
    assert task["title"] == NOODLE and task["must_confirm"] is True and task["urgent"] is False
    donna.turn("응")  # 한 번 더 "응"해도 두 번 넣지 않는다
    assert len(review_tasks()) == 1


def test_two_items_and_drop_the_second():
    donna = morning()
    add_seal()
    briefing.prepare("s005")
    asked = to_tasks_step(donna)
    assert [s["text"] for s in asked["say"]][0] == "알바생 할 일로 넣을 게 두 개 있어요."
    assert [i["title"] for i in asked["cards"][0]["items"]] == [f"1. {NOODLE}", "2. 배달 용기 이중 실링"]
    edited = donna.turn("두 번째는 빼")
    assert edited["intent"] == "action.edit" and edited["type"] == "ask_tasks"
    assert [s["text"] for s in edited["say"]] == [f"둘째는 빼고, {NOODLE}를 넣을까요?"]
    donna.turn("응")
    assert [t["title"] for t in review_tasks()] == [NOODLE]
    assert hr_log() == [("review_fix_task", "rejected"), ("review_fix_task", "approved")]  # 뺀 건만 반려, 건마다 센다


def test_drop_and_put_in_one_sentence():
    donna = morning()
    add_seal()
    briefing.prepare("s005")
    to_tasks_step(donna)
    done = donna.turn("첫 번째는 빼고 넣어")
    assert done["intent"] == "action.approve" and [t["title"] for t in review_tasks()] == ["배달 용기 이중 실링"]
    assert sorted(hr_log()) == [("review_fix_task", "approved"), ("review_fix_task", "rejected")]


def test_no_puts_nothing():
    donna = morning()
    to_tasks_step(donna)
    done = donna.turn("안 해")
    assert done["intent"] == "action.cancel" and done["say"][0]["text"] == "네, 알바생 할 일은 넣지 않을게요."
    assert review_tasks() == []
    assert hr_log() == [("review_fix_task", "rejected")]


def test_missed_in_briefing_is_asked_on_next_call_then_the_call_is_answered():
    """브리핑을 듣지 않았으면 그날 처음 '도나야'로 부를 때 먼저 묻고, 대답한 뒤 원래 물은 말에 답한다 (2026-11-20 결정)."""
    donna = morning()
    donna.clock("2026-11-17T15:35:00+09:00")
    first = donna.turn("하린이 초대해 줘", addressed=True)
    assert first["type"] == "ask_tasks" and first["say"][0]["text"] == "그 전에 하나만요."
    done = donna.turn("응, 넣어")
    texts = [s["text"] for s in done["say"]]
    assert texts[0] == f"알바생 할 일에 {NOODLE}를 넣었어요." and done["intent"] == "action.approve"
    assert any("초대" in t or "코드" in t for t in texts[2:])  # 이어서 원래 말(초대)에 답했다
    assert [t["title"] for t in review_tasks()] == [NOODLE]
    later = donna.turn("하린이 초대해 줘", addressed=True)
    assert later["type"] != "ask_tasks"  # 다시 묻지 않는다


def test_called_briefing_is_not_cut_in_and_asks_at_the_end():
    """'도나야, 브리핑해 줘'는 앞에서 가로채지 않는다. 브리핑 마지막 단계에서 묻는다 (2026-11-21, 시연이 이렇게 시작한다)."""
    donna = morning()
    first = donna.turn("오늘 일정 브리핑해 줘", addressed=True)
    assert first["intent"] == "briefing.start" and first["type"] != "ask_tasks"
    assert "그 전에 하나만요." not in [s["text"] for s in first["say"]]
    response = first
    for _ in range(12):
        if response["type"] == "ask_tasks":
            break
        response = donna.turn("다음")
    assert response["type"] == "ask_tasks" and response["briefing"]["step_key"] == "staff_tasks"


# ── 예약 손님 요청사항에서 나온 할 일 (Figma v0.2.1 H-11 · H-12) ──


def test_reservation_memo_is_asked_with_the_memo_and_shown_when_put_in():
    donna = morning(keep="field_variable")
    asked = to_tasks_step(donna)
    assert asked["headline"] == "알바생 할 일에 넣을까요?" and asked["expects_reply"] is True
    assert [s["text"] for s in asked["say"]] == ["12시 예약 손님 중 한 분이 땅콩 알레르기가 있어요.", "알바생 할 일에 넣을까요?"]
    rows, memo = asked["cards"]
    assert [(r["kind"], r["value"]) for r in rows["rows"]] == [
        ("reservation", "낮 12시 12명 예약"), ("warning", "땅콩 알레르기 손님 1명"), ("person", "오늘 나온 사람 모두"), ("time", "오늘만")]
    assert memo == {"type": "quote", "id": "staff_task_memo", "label": "예약 손님이 적은 요청사항", "text": "“땅콩 알레르기 손님 1명 있어요”"}

    done = donna.turn("응, 넣어")
    assert done["intent"] == "action.approve" and done["type"] == "answer" and done["headline"] == "알바생 할 일에 넣었어요"
    assert [s["text"] for s in done["say"]] == ["알바생 할 일에 넣었어요."]
    assert [c["type"] for c in done["cards"]] == ["rows"] and done["cards"][0]["note"] == "알바생 할 일에 넣음"
    assert done["briefing"]["step_key"] == "staff_tasks"  # 브리핑 중 대답: 가만히 있으면 끝으로 넘어간다
    [task] = [t for t in staff.store_tasks("s005") if t["origin"] == "field_variable"]
    assert task["title"] == "12시 손님 땅콩 알레르기" and task["urgent"] is True  # 오늘 손님이 바로 겪는 일
    end = donna.turn(event="auto_next")
    assert end["type"] == "end" and [r["value"] for r in end["cards"][0]["rows"]] == ["12시 손님 땅콩 알레르기"]
    for response in (asked, done, end):
        assert width.violations(response) == []


def test_not_asked_after_close_and_expired_next_day():
    donna = morning()
    donna.clock("2026-11-17T21:00:00+09:00")  # 문 닫은 뒤에는 묻지 않는다
    assert donna.turn("오늘 예약 몇 팀이야?", addressed=True)["type"] != "ask_tasks"
    donna.clock("2026-11-18T09:30:00+09:00")  # 다음 날 준비 → 어제 못 물은 제안은 버린다
    briefing.prepare("s005")
    assert {p["state"] for p in proposals.for_briefing("s005", "2026-11-17", include_asked=True)} == set()
    assert review_tasks() == []


# ── 대답하지 않은 "그 전에 하나만요"의 원래 말은 버린다 (2026-11-22 버그 V6) ──


def test_unanswered_cut_in_does_not_replay_the_call_later():
    from voice import staff_db

    donna = morning()
    donna.clock("2026-11-17T15:35:00+09:00")
    assert donna.turn("하린이 초대해 줘", addressed=True)["say"][0]["text"] == "그 전에 하나만요."
    assert donna.turn("오늘 예약 몇 팀이야?")["intent"] == "question"  # 할 일 질문에 대답하지 않고 넘어갔다
    invites = staff_db.invites_of("st_harin")
    donna.clock("2026-11-18T09:30:00+09:00")
    briefing.prepare("s005")
    add_seal("rv_y")
    briefing.prepare("s005")
    to_tasks_step(donna)
    yes = donna.turn("응, 넣어")
    assert yes["intent"] == "action.approve" and not any("초대" in s["text"] for s in yes["say"])
    assert staff_db.invites_of("st_harin") == invites


def test_unanswered_cut_in_is_not_replayed_by_a_later_briefing_the_same_day():
    from voice import staff_db

    donna = morning()
    donna.clock("2026-11-17T15:35:00+09:00")
    donna.turn("하린이 초대해 줘", addressed=True)
    donna.turn("오늘 예약 몇 팀이야?")
    invites = staff_db.invites_of("st_harin")
    add_seal("rv_y")
    briefing.prepare("s005")
    to_tasks_step(donna)
    yes = donna.turn("응, 넣어")
    assert yes["intent"] == "action.approve" and not any("초대" in s["text"] for s in yes["say"])
    assert staff_db.invites_of("st_harin") == invites


def test_deferred_text_cleared_on_new_day():
    """어제 "그 전에 하나만요"에 대답하지 않았으면, 날짜가 바뀐 뒤 같은 세션의 첫 말에서 원래 말을 버린다 (2026-11-22 버그 V13)."""
    from voice import repo

    donna = morning()
    donna.clock("2026-11-17T15:35:00+09:00")
    assert donna.turn("하린이 초대해 줘", addressed=True)["say"][0]["text"] == "그 전에 하나만요."
    assert repo.get("session", donna.session_id)["deferred_text"] == "하린이 초대해 줘"
    donna.clock("2026-11-18T09:30:00+09:00")
    assert donna.turn("3번 테이블 치워 줘")["type"] == "ignore"  # 흘려듣는 말이어도 날짜가 바뀌었으면 비운다
    assert "deferred_text" not in repo.get("session", donna.session_id)


def test_kitchen_talk_after_cut_in_still_answers_the_call():
    donna = morning()
    donna.clock("2026-11-17T15:35:00+09:00")
    donna.turn("하린이 초대해 줘", addressed=True)
    assert donna.turn("3번 테이블 치워 줘")["type"] == "ignore"
    done = donna.turn("응, 넣어")
    assert any("초대" in s["text"] for s in done["say"])
