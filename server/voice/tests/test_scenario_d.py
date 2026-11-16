"""시나리오 D: 비어 있을 때, 그리고 모든 응답의 글자 폭 (D4). 문서 13장."""

import time

from voice import width
from voice.tests.conftest import Donna, baseline, prepared

AWAITING = {"rv_0412", "rv_0405", "rv_0409", "rv_0410", "rv_0408"}


def test_d1_nothing_scheduled_today():
    payload = baseline()
    payload["events"], payload["games"], payload["reservations"] = [], [], []
    d1 = prepared(payload).turn("오늘 일정 브리핑해 줘")
    assert d1["headline"] == "오늘은 평소와 같아요" and d1["cards"] == [] and d1["briefing"]["step"] == 1


def test_d2_no_reviews_waiting_skips_steps_2_and_3():
    payload = baseline()
    for review in payload["reviews"]:
        if review["id"] in AWAITING:
            review.update(reply_status="posted", reply_by="owner", reply_text="감사해요!", reply_posted_at="2026-11-17T08:00:00+09:00")
    donna = prepared(payload)
    donna.turn("오늘 일정 브리핑해 줘")
    d2 = donna.turn("다음")
    assert d2["briefing"]["step"] == 3  # 리뷰 칸을 건너뛰어 게이지바가 한꺼번에 두 칸 찬다
    d3 = donna.turn("다음")  # 예약할 좋은 리뷰도 없어 5단계도 건너뛴다
    assert d3["type"] == "end"
    assert "p_reviews" not in [r["id"] for r in donna.home()["cards"][0]["rows"]]


def test_d3_no_scheduled_replies_goes_to_end():
    payload = baseline()
    for review in payload["reviews"]:
        if review["id"] in {"rv_0409", "rv_0410", "rv_0408"}:
            review.update(reply_status="posted", reply_by="owner", reply_text="감사해요!", reply_posted_at="2026-11-17T08:00:00+09:00")
    donna = prepared(payload, permission=True)  # 허락했지만 바로 답한 리뷰가 없어 3단계도 건너뛴다
    steps = [donna.turn("오늘 일정 브리핑해 줘")["briefing"]["step"]]
    while True:
        response = donna.turn("다음")
        if response["type"] == "end":
            break
        steps.append(response["briefing"]["step"])
    assert steps == [1, 2, 3]


def test_d4_every_response_fits_the_screen():
    """여러 갈래로 대화하며 받은 모든 응답(홈 포함)에 한도를 넘는 칸이 없다."""
    flows = [
        (None, ["오늘 일정 브리핑해 줘", "화면에 보여 줘", "읽어 줘", "돌아가기", "다음", "다시 말해 줘", "다음", "아니 내가 볼게",
                "화면에 보여 줘", "다음", "화면에 보여 줘", "읽어 줘", "돌아가기", "다음", "처음부터 다시", "리뷰 보여 줘",
                "좋은 리뷰 어때", "예약 답글은", "내일 예약 있어?", "이번 주 비 와?", "그만"]),
        (False, ["오늘 일정 브리핑해 줘", "다음", "다음", "화면에 보여 줘", "읽어 줘", "됐어", "다음", "다음", "다음"]),
    ]
    for permission, texts in flows:
        donna = prepared(permission=permission)
        responses = [donna.home()] + [donna.turn(text) for text in texts]
        for response in responses:
            assert width.violations(response) == [], (response.get("headline"), width.violations(response))
        # say 는 한 문장씩 (리뷰·답글 원문을 그대로 읽는 detail.read 는 빼고)
        for response in responses:
            if response.get("intent") == "detail.read":
                continue
            for line in response.get("say") or []:
                assert ". " not in line["text"], line["text"]


def test_question_answers_from_known_data(donna: Donna):
    tomorrow = donna.turn("내일 예약 있어?")
    assert tomorrow["intent"] == "question" and tomorrow["headline"] == "내일은 예약이 없어요" and tomorrow["briefing"] is None
    rain = donna.turn("이번 주 비 와?")
    assert rain["headline"] == "목요일에 비 소식이 있어요"


def test_briefing_turn_is_fast(donna: Donna):
    started = time.perf_counter()
    for text in ("오늘 일정 브리핑해 줘", "다음", "다음", "응 그렇게 해", "다음", "다음"):
        donna.turn(text)
    assert (time.perf_counter() - started) / 6 < 1.0  # 브리핑 단계는 1초 안 (문서 11장)
