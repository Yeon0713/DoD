"""F8 뜻 알아듣기 규칙 (LLM 없이)."""

import pytest

from voice.dialog.intent_rules import heuristic, match


@pytest.mark.parametrize("text, last_type, intent", [
    ("오늘 일정 브리핑해 줘", None, "briefing.start"),
    ("브리핑해 주세요", None, "briefing.start"),
    ("브리핑", None, "briefing.start"),
    ("오늘 뭐 있어", None, "briefing.start"),
    ("오늘 일정 부리핑 해줘", None, "briefing.start"),
    ("다음", "answer", "briefing.next"),
    ("넘어가", "answer", "briefing.next"),
    ("계속", "answer", "briefing.next"),
    ("다시 말해 줘", "answer", "briefing.repeat"),
    ("뭐라고?", "answer", "briefing.repeat"),
    ("처음부터 다시", "end", "briefing.restart"),
    ("리뷰 어때", "answer", "briefing.jump"),
    ("리뷰 보여 줘", "end", "briefing.jump"),
    ("예약 답글은", "answer", "briefing.jump"),
    ("화면에 보여 줘", "answer", "detail.show"),
    ("자세히 보여 줘", "answer", "detail.show"),
    ("읽어 줘", "show_detail", "detail.read"),
    ("돌아가기", "show_detail", "detail.back"),
    ("됐어", "show_detail", "detail.back"),
    ("됐어", "ask_permission", "permission.no"),  # 같은 말이 상황에 따라 다른 뜻
    ("응 그렇게 해", "ask_permission", "permission.yes"),
    ("그래", "ask_permission", "permission.yes"),
    ("좋아", "ask_permission", "permission.yes"),
    ("아니 내가 볼게", "ask_permission", "permission.no"),
    ("아니", "ask_permission", "permission.no"),
    ("그만", "answer", "stop"),
    ("됐어 그만해", "answer", "stop"),
    ("내일 예약 있어?", None, "question"),
    ("이번 주 비 와?", None, "question"),
    ("3번 테이블 치워 줘", "answer", "not_for_donna"),
    ("어서 오세요 몇 분이세요", "ask_permission", "not_for_donna"),  # '어'로 시작해도 허락 대답이 아니다
    ("네 손님 잠시만요", "ask_permission", "not_for_donna"),
])
def test_rules(text, last_type, intent):
    found = match(text, last_type)
    assert found is not None and found.name == intent, (text, found)


def test_jump_targets():
    assert match("리뷰 어때", "answer").jump_to == "reviews"
    assert match("좋은 리뷰 어때", "answer").jump_to == "positive"
    assert match("아쉬운 리뷰 보여 줘", "answer").jump_to == "negative"
    assert match("예약 답글은", "answer").jump_to == "scheduling"


def test_unclear_words_go_to_llm_then_heuristic():
    assert match("그거 뭐였지 그 저기", "answer") is None
    assert heuristic("그거 뭐였지 그 저기").name == "unknown"
    assert match("오늘 국이 좀 짜네", "answer") is None
    assert heuristic("오늘 국이 좀 짜네").name == "not_for_donna"  # 애매하면 가만히


def test_owner_said_is_tidied():
    assert match("오늘 일정 부리핑 해조", None).owner_said == "오늘 일정 브리핑해 줘"
    assert match("응 그렇게 해", "ask_permission").owner_said == "응, 그렇게 해"
    assert match("다음", "answer").owner_said == "다음"
