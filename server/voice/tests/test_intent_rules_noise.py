"""뜻 규칙(dialog/intent_rules)의 받아쓰기 오류 대응과 부른 질문 꼴.

- near_words: 자모 한두 개가 바뀐 명령 낱말을 되돌린다. 흔한 말(NEAR_PROTECT)은 바꾸지 않는다.
- SHOW_RE: "화면 보여 줘"처럼 조사가 빠져도 자세히 보기.
- asks_donna: "도나야"로 부른 질문 꼴(~까, ~니, ~야, ?)은 question. 부르지 않은 질문은 규칙이 가르지 않는다 (직원끼리 한 말일 수 있다).
"""

import pytest

from voice.dialog import intent_rules as rules


@pytest.mark.parametrize("heard, fixed", [
    ("따음", "다음"), ("릐뷰", "리뷰"), ("첨부터다시해줘", "처음부터다시해줘"), ("계소", "계속"), ("일거줘", "읽어줘"),
])
def test_near_words_restores_command_words(heard, fixed):
    assert rules.near_words(heard) == fixed


def test_near_words_keeps_common_words_and_exact_words():
    assert rules.near_words("뭐부터하면좋을까") == "뭐부터하면좋을까"  # "하면"은 "화면"으로 바꾸지 않는다
    assert rules.near_words("다음") == "다음" and rules.near_words("3번테이블치워줘") == "3번테이블치워줘"


@pytest.mark.parametrize("text, last_type, name", [
    ("따음", "answer", "briefing.next"),
    ("첨부터 해 줘", "answer", "briefing.restart"),
    ("화면 보여 줘", "answer", "detail.show"),
    ("리부 어때", "answer", "briefing.jump"),
])
def test_noisy_commands_are_understood(text, last_type, name):
    found = rules.match(text, last_type)
    assert found is not None and found.name == name


def test_addressed_question_form_is_a_question():
    for text in ("오늘 바쁠까", "뭐부터 할까", "내일 매출 오늘보다 나을까", "오늘 장사 잘될까?"):
        found = rules.match(text, None, addressed=True)
        assert found is not None and found.name == "question", text


def test_unaddressed_question_form_is_left_to_the_judge():
    assert rules.match("리뷰 이벤트 서비스 드릴까?", "answer") is None  # 직원끼리 한 말일 수 있다
    assert rules.match("손님 자리 안내할까?", "answer").name == "not_for_donna"
    assert rules.match("다음", "answer", addressed=True).name == "briefing.next"  # 명령은 그대로
