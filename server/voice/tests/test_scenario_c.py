"""시나리오 C: 말 알아듣기 (브리핑 첫 요약 줄을 말하는 중). 문서 13장. 에이전트는 꺼져 있어 규칙만으로 통과해야 한다.
v0.2.1 H: 요약 세 줄(sum_*) → "상세 브리핑을 시작할까요?"(detail_ask) → 상세. 기준 데이터는 비가 없어 요약은 리뷰 줄부터다."""

from voice import context
from voice.tests.conftest import Donna


def at_step_one(donna: Donna) -> dict:
    return donna.turn("오늘 일정 브리핑해 줘")


def test_c1_repeat(donna: Donna):
    first = at_step_one(donna)
    c1 = donna.turn("다시 말해 줘")
    assert c1["type"] == "answer" and c1["briefing"]["step"] == 1 and c1["headline"] == "다시 말씀드릴게요"
    assert c1["say"][0]["text"] == "다시 말씀드릴게요." and c1["say"][1:] == first["say"] and "suggestions" not in c1


def test_c2_typo(donna: Donna):
    c2 = donna.turn("오늘 일정 부리핑 해조")
    assert c2["intent"] == "briefing.start" and c2["owner_said"] == "오늘 일정 브리핑해 줘"


def test_c3_c4_not_for_donna_is_ignored(donna: Donna):
    at_step_one(donna)
    for text in ("3번 테이블 치워 줘", "어서 오세요 몇 분이세요"):
        response = donna.turn(text)
        assert response["type"] == "ignore" and response["say"] == [] and response["cards"] == [] and response["headline"] is None
    # 무시한 말은 진행 상태를 바꾸지 않는다 (요약 다음 줄로 한 칸만)
    assert donna.turn("다음")["briefing"]["step_key"] == "sum_resv"


def test_c5_c6_not_understood_and_stop(donna: Donna):
    at_step_one(donna)
    c5 = donna.turn("그거 뭐였지 그 저기")
    assert c5["type"] == "not_understood" and c5["say"] == [] and "suggestions" not in c5
    c6 = donna.turn("그만")
    assert c6["type"] == "stop" and c6["intent"] == "stop" and c6["cards"] == []


def test_c7_jump(donna: Donna):
    at_step_one(donna)
    c7 = donna.turn("리뷰 어때")  # 상세 브리핑 물음을 건너뛰고 리뷰 칸으로
    assert c7["intent"] == "briefing.jump" and c7["type"] == "answer" and c7["briefing"] == {"step": 3, "total": 4, "step_key": "reviews"}
    # 예전 단계 이름: 좋은 리뷰(positive)는 리뷰 칸으로 간다
    positive = donna.turn("좋은 리뷰 어때")
    assert positive["intent"] == "briefing.jump" and positive["briefing"]["step_key"] == "reviews"


def test_c8_barge_in_moves_on(donna: Donna):
    first = at_step_one(donna)
    c8 = donna.turn("다음", donna_was_speaking=True, heard_until={"turn_id": first["turn_id"], "say_index": 1})
    assert c8["type"] == "answer" and c8["briefing"]["step_key"] == "sum_resv"


def test_c9_same_request_id_same_response(donna: Donna):
    a = donna.turn("오늘 일정 브리핑해 줘", request_id="req_7f3a2c")
    b = donna.turn("오늘 일정 브리핑해 줘", request_id="req_7f3a2c")
    assert a == b
    nxt = donna.turn("다음", request_id="req_next")
    again = donna.turn("다음", request_id="req_next")  # 통신이 끊겨 다시 보낸 경우
    assert nxt == again and nxt["briefing"]["step_key"] == "sum_resv"
    assert donna.turn("다음")["briefing"]["step_key"] == "detail_ask"  # 두 번 넘어가지 않았다


def test_no_chips_in_v021(donna: Donna):
    """v0.2.1 부터 칩이 없다. 칩으로 보낸 요청은 받지 않는다."""
    at_step_one(donna)
    donna.turn("다음", source="chip", expect=422)


def test_addressed_speech_is_never_ignored(donna: Donna):
    """"도나야"로 부른 말은 손님·직원에게 한 말로 넘기지 않는다."""
    at_step_one(donna)
    assert donna.turn("3번 테이블 치워 줘")["type"] == "ignore"
    assert donna.turn("3번 테이블 치워 줘", addressed=True)["type"] == "not_understood"
    assert donna.turn("손님 다음", addressed=True)["type"] != "ignore"


def test_navigate_opens_tabs(donna: Donna):
    sales = donna.turn("매출 어때")
    assert sales["type"] == "navigate" and sales["tab"] == "sales" and sales["intent"] == "navigate.sales" and sales["briefing"] is None
    week = donna.turn("이번 주 보여 줘")
    assert week["tab"] == "week" and week["say"][0]["text"].startswith("이번 주는")
    assert donna.turn("설정 열어 줘")["tab"] == "settings"
    assert donna.turn("이번 주 비 와?")["intent"] == "question"  # 묻는 말은 탭을 열지 않는다


def test_briefing_turns_never_call_clova(donna: Donna):
    for text in ("오늘 일정 브리핑해 줘", "다음", "다시 말해 줘", "화면에 보여 줘", "돌아가기", "리뷰 어때", "다음", "응 그렇게 해", "다음", "다음"):
        donna.turn(text)
    assert context.post.calls == 0


def test_read_negative_review_moves_and_reads_first(donna: Donna):
    at_step_one(donna)
    donna.turn("아쉬운 리뷰 어때")  # 3단계: 써 둔 사과 답변을 올릴까요? (부정 리뷰 답글 인턴, 인사과 4-a)
    donna.turn("아니 내가 볼게")  # 올리지 않으면 초안으로 남는다
    response = donna.turn("아쉬운 리뷰 읽어줘")
    assert response["intent"] == "detail.read" and response["briefing"]["step_key"] == "negative"
    assert response["say"][0]["text"] == "손님 리뷰예요."


def test_read_negative_review_reads_the_draft_being_asked(donna: Donna):
    at_step_one(donna)  # 3단계가 "올릴까요?"로 묻는 중이다 (허락 질문 D-10 은 없앰)
    response = donna.turn("아쉬운 리뷰 읽어줘")
    assert response["briefing"]["step_key"] == "negative" and response["say"][0]["text"] == "손님 리뷰예요."
    assert response["say"][2]["text"] == "제가 써 둔 답글 초안이에요."
