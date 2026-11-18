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


# G3·G4 (donna-voice/docs/test-scenarios-closed-loop.md): 아쉬운 리뷰 처리를 물은 뒤(ask_action). 잘못 실행하지 않는 쪽으로 가른다.
@pytest.mark.parametrize("text, addressed, intent, edits", [
    ("응, 진행해", False, "action.approve", (False, False)),
    ("그렇게 해", False, "action.approve", (False, False)),
    ("올려", False, "action.approve", (False, False)),
    ("네 진행해 주세요", False, "action.approve", (False, False)),
    ("응 그거 냉장고에 넣어", False, None, None),  # G3: 문장 전체가 승인 말이 아니면 승인이 아니다
    ("네", False, "action.unclear", None),  # G4: 부르지 않은 "네"는 손님 대답일 수 있다
    ("어", False, "action.unclear", None),
    ("네", True, "action.approve", (False, False)),
    ("쿠폰 빼고 사과만 올려", False, "action.approve", (True, False)),
    ("카드는 넣지 마", False, "action.edit", (False, True)),
    ("아니, 서비스는 빼", False, "action.edit", (True, False)),  # "아니"로 시작해도 고치는 말이면 취소가 아니다
    ("사과만 올리고 카드도 빼", False, "action.approve", (True, True)),
    ("안 해", False, "action.cancel", None),
    ("내가 쓸게", False, "action.cancel", None),
    ("3번 테이블 치워 줘", False, "not_for_donna", None),
    ("네 손님 포장이세요?", False, "not_for_donna", None),
])
def test_ask_action(text, addressed, intent, edits):
    found = match(text, "ask_action", addressed)
    assert (found.name if found else None) == intent
    if edits is not None:
        assert (found.edits["drop_compensation"], found.edits["no_card"]) == edits


# 부른 말의 질문 꼴은 가게 말 규칙보다 먼저 본다. 부르지 않은 "~(ㄹ)까" 질문은 탭을 열지 않고 판정 에이전트에 맡긴다
@pytest.mark.parametrize("text, addressed, intent", [
    ("도나야 오늘 손님 많을까", False, "question"),  # 앱이 떼지 못한 호출어
    ("도나 와", False, None),  # 호출어가 아니다 (어림짐작이 not_for_donna)
    ("오늘 손님 많을까", False, "not_for_donna"),
    ("오늘 장사 잘될까", False, None),
    ("이번 주말에 비 올까", False, None),
    ("오늘 장사 잘될까", True, "question"),
    ("이번 주 매출 어때", False, "navigate.sales"),
])
def test_called_question_and_unaddressed_guess(text, addressed, intent):
    found = match(text, None, addressed)
    assert (found.name if found else None) == intent


# 대상(리뷰 등)을 같이 말하면 다시 말하기·지금 화면 읽기로 정하지 않는다. 아쉬운 리뷰 내용을 물으면 그리로 옮겨 첫 리뷰를 읽는다
@pytest.mark.parametrize("text, last_type, intent, jump_to", [
    ("아쉬운 리뷰 읽어줘", None, "detail.read", "negative"),
    ("아쉬운 리뷰 읽어줘", "show_detail", "detail.read", "negative"),
    ("아쉬운 리뷰 뭐라고 썼어?", "answer", "detail.read", "negative"),
    ("아쉬운 리뷰 내용 좀 알려줘", None, "detail.read", "negative"),
    ("리뷰 뭐라고 했어?", "answer", None, None),  # 판정 에이전트에 맡긴다
    ("다시 말해 줘", "answer", "briefing.repeat", None),
    ("읽어 줘", "show_detail", "detail.read", None),
    ("손님 리뷰 읽어 줘", "show_detail", "detail.read", None),  # 띄운 리뷰를 읽는 말
    ("리뷰 읽어 줘", "answer", None, None),
])
def test_target_with_repeat_or_read(text, last_type, intent, jump_to):
    found = match(text, last_type, addressed=True)
    assert (found.name if found else None) == intent
    assert (found.jump_to if found else None) == jump_to


# 부르지 않은 "~까" 질문은 묻는 말로도 정하지 않는다. 물건 자리를 묻는 말은 탭보다 가게 말이 먼저다
@pytest.mark.parametrize("text, addressed, intent", [
    ("날씨 추운데 문 닫을까?", False, None),
    ("이번 주 비 와?", False, "question"),
    ("매출 장부 어디 뒀니?", False, "not_for_donna"),
    ("설정 어디 있어", False, "not_for_donna"),
    ("매출 장부 어디 뒀니?", True, "question"),  # 부른 말은 무시하지 않는다
])
def test_unaddressed_guess_and_where(text, addressed, intent):
    found = match(text, None, addressed)
    assert (found.name if found else None) == intent


@pytest.mark.parametrize("name, text, addressed, expected", [
    ("unknown", "그거 뭐였지 그 저기", False, "unknown"),  # 도나에게 묻는 말 (문서 13장 C5: not_understood)
    ("unknown", "두 분이세요", False, "not_for_donna"),  # 부르지 않았고 도나에게 묻는 말도 아니면 가만히
    ("unknown", "도나야 그 뭐냐", False, "unknown"),  # 글자에 남은 호출어
    ("unknown", "그 뭐냐", True, "unknown"),
    ("question", "오늘 바쁠까", False, "question"),
])
def test_judge_unknown_on_unaddressed_is_silent(name, text, addressed, expected):
    from voice.dialog.intent_rules import unknown_to_silent

    assert unknown_to_silent(name, text, addressed) == expected


def test_near_words_keep_honorific_hasi():
    # "주문하시겠어요"의 "하시"를 "다시"로 고치면 가게 말 규칙(주문하시)을 놓친다
    assert match("주문하시겠어요?", "answer").name == "not_for_donna"
