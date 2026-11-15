"""시나리오 C: 말 알아듣기 (브리핑 1단계를 말하는 중). 문서 13장. 에이전트는 꺼져 있어 규칙만으로 통과해야 한다."""

from voice import context
from voice.tests.conftest import Donna


def at_step_one(donna: Donna) -> dict:
    return donna.turn("오늘 일정 브리핑해 줘")


def test_c1_repeat(donna: Donna):
    first = at_step_one(donna)
    c1 = donna.turn("다시 말해 줘")
    assert c1["type"] == "answer" and c1["briefing"]["step"] == 1 and c1["headline"] == "다시 말씀드릴게요"
    assert c1["say"] == first["say"] and c1["suggestions"] == ["다음", "그만"]


def test_c2_typo(donna: Donna):
    c2 = donna.turn("오늘 일정 부리핑 해조")
    assert c2["intent"] == "briefing.start" and c2["owner_said"] == "오늘 일정 브리핑해 줘"


def test_c3_c4_not_for_donna_is_ignored(donna: Donna):
    at_step_one(donna)
    for text in ("3번 테이블 치워 줘", "어서 오세요 몇 분이세요"):
        response = donna.turn(text)
        assert response["type"] == "ignore" and response["say"] == [] and response["cards"] == [] and response["headline"] is None
    # 무시한 말은 진행 상태를 바꾸지 않는다
    assert donna.turn("다음")["briefing"]["step"] == 2


def test_c5_c6_not_understood_and_stop(donna: Donna):
    at_step_one(donna)
    c5 = donna.turn("그거 뭐였지 그 저기")
    assert c5["type"] == "not_understood" and c5["say"] == [] and c5["suggestions"] == []
    c6 = donna.turn("그만")
    assert c6["type"] == "stop" and c6["intent"] == "stop" and c6["cards"] == []


def test_c7_jump(donna: Donna):
    at_step_one(donna)
    c7 = donna.turn("리뷰 어때")
    assert c7["intent"] == "briefing.jump" and c7["type"] == "answer" and c7["briefing"]["step"] == 2


def test_c8_barge_in_moves_on(donna: Donna):
    first = at_step_one(donna)
    c8 = donna.turn("다음", donna_was_speaking=True, heard_until={"turn_id": first["turn_id"], "say_index": 1})
    assert c8["type"] == "answer" and c8["briefing"]["step"] == 2


def test_c9_same_request_id_same_response(donna: Donna):
    a = donna.turn("오늘 일정 브리핑해 줘", request_id="req_7f3a2c")
    b = donna.turn("오늘 일정 브리핑해 줘", request_id="req_7f3a2c")
    assert a == b
    nxt = donna.turn("다음", request_id="req_next")
    again = donna.turn("다음", request_id="req_next")  # 통신이 끊겨 다시 보낸 경우
    assert nxt == again and nxt["briefing"]["step"] == 2
    assert donna.turn("다음")["briefing"]["step"] == 3  # 두 번 넘어가지 않았다


def test_chips_send_the_same_request(donna: Donna):
    at_step_one(donna)
    chip = donna.turn("다음", source="chip")
    assert chip["briefing"]["step"] == 2 and chip["owner_said"] == "다음"


def test_briefing_turns_never_call_clova(donna: Donna):
    for text in ("오늘 일정 브리핑해 줘", "다음", "다시 말해 줘", "화면에 보여 줘", "돌아가기", "리뷰 어때", "다음", "응 그렇게 해", "다음", "다음"):
        donna.turn(text)
    assert context.post.calls == 0
