"""알바생 할 일 묻기 (jobs/staff_tasks.py, 에이전트 조직 개편 3단계).

초옹장 11/17 아침: 밤사이 아쉬운 리뷰(면 불음, 옹심이 퍼짐)에서 같은 교정 카드 하나가 나와 브리핑 마지막에 묻는다.
"""

from voice import clock, proposals, staff
from voice.jobs import briefing
from voice.tests.conftest import choongjang

SEAL = {"title": "배달 용기 이중 실링", "detail": "국물 메뉴는 랩을 두 번 씌우고 뚜껑에 테이프를 한 번 더 붙여 주세요",
        "phase": "open", "days": 2, "must_confirm": True, "urgent": False}
NOODLE = "배달 칼국수 면·국물 따로 담기"


def morning():
    """초옹장 11/17 09:02, 할 일 제안을 그대로 둔 채."""
    return choongjang(keep_tasks=True, at=None)


def to_tasks_step(donna) -> dict:
    response = donna.turn("오늘 일정 브리핑해 줘")
    for _ in range(8):
        if response["type"] == "ask_tasks":
            return response
        response = donna.turn("다음")
    raise AssertionError("할 일 묻기 단계가 없어요")


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


def test_drop_and_put_in_one_sentence():
    donna = morning()
    add_seal()
    briefing.prepare("s005")
    to_tasks_step(donna)
    done = donna.turn("첫 번째는 빼고 넣어")
    assert done["intent"] == "action.approve" and [t["title"] for t in review_tasks()] == ["배달 용기 이중 실링"]


def test_no_puts_nothing():
    donna = morning()
    to_tasks_step(donna)
    done = donna.turn("안 해")
    assert done["intent"] == "action.cancel" and done["say"][0]["text"] == "네, 알바생 할 일은 넣지 않을게요."
    assert review_tasks() == []


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
    for _ in range(8):
        if response["type"] == "ask_tasks":
            break
        response = donna.turn("다음")
    assert response["type"] == "ask_tasks" and response["briefing"]["step_key"] == "staff_tasks"


def test_not_asked_after_close_and_expired_next_day():
    donna = morning()
    donna.clock("2026-11-17T21:00:00+09:00")  # 문 닫은 뒤에는 묻지 않는다
    assert donna.turn("오늘 예약 몇 팀이야?", addressed=True)["type"] != "ask_tasks"
    donna.clock("2026-11-18T09:30:00+09:00")  # 다음 날 준비 → 어제 못 물은 제안은 버린다
    briefing.prepare("s005")
    assert {p["state"] for p in proposals.for_briefing("s005", "2026-11-17", include_asked=True)} == set()
    assert review_tasks() == []
