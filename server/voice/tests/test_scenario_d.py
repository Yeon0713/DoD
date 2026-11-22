"""시나리오 D: 비어 있을 때, 그리고 모든 응답의 글자 폭 (D4). 문서 13장."""

import time

from voice import width
from voice.tests.conftest import Donna, baseline, prepared, walk_to

AWAITING = {"rv_0412", "rv_0405", "rv_0409", "rv_0410", "rv_0408"}


def test_d1_nothing_scheduled_today():
    """행사·경기·예약이 없으면 요약에 일정 줄이 없다. 밤사이 리뷰도 없으면 요약 없이 "오늘은 평소와 같아요"로 바로 묻는다 (H-05)."""
    payload = baseline()
    payload["events"], payload["games"], payload["reservations"] = [], [], []
    donna = prepared(payload)
    assert donna.home()["cards"][0]["rows"][0] == {"id": "p_schedule", "kind": "schedule", "value": "평소와 같아요"}
    d1 = donna.turn("오늘 일정 브리핑해 줘")
    assert d1["briefing"]["step_key"] == "sum_reviews" and [r["kind"] for r in d1["cards"][0]["rows"]] == ["reviews"]
    assert donna.turn("다음")["briefing"]["step_key"] == "detail_ask"  # 예약 줄(sum_resv)이 없다

    payload["reviews"] = []
    empty = prepared(payload).turn("오늘 일정 브리핑해 줘")
    assert empty["type"] == "ask" and empty["briefing"] == {"step": 1, "total": 4, "step_key": "detail_ask"}
    assert empty["headline"] == "오늘은 평소와 같아요" and empty["cards"] == []
    assert [s["text"] for s in empty["say"]] == ["오늘은 행사나 예약이 없어요.", "상세 브리핑을 시작할까요?"]


def test_d2_no_reviews_waiting_skips_reply_steps():
    """답글 기다리는 리뷰가 없으면 밤사이 리뷰 수만 알리고, 예약한 답글(H-09)·아쉬운 리뷰 단계를 건너뛴다."""
    payload = baseline()
    for review in payload["reviews"]:
        if review["id"] in AWAITING:
            review.update(reply_status="posted", reply_by="owner", reply_text="감사해요!", reply_posted_at="2026-11-17T08:00:00+09:00")
    donna = prepared(payload)
    d2 = walk_to(donna, "reviews")
    assert d2["briefing"]["step"] == 3 and d2["headline"] == "리뷰 4건이 도착했습니다"  # 사장님이 이미 답한 리뷰도 도착한 리뷰로 센다
    d3 = donna.turn("다음")
    assert d3["briefing"]["step_key"] == "staff_tasks"  # 답글 단계는 모두 건너뛰어 알바생 할 일로
    assert "p_replies" not in [r["id"] for r in donna.home()["cards"][0]["rows"]]


def test_d3_no_scheduled_replies_goes_to_end():
    payload = baseline()
    for review in payload["reviews"]:
        if review["id"] in {"rv_0409", "rv_0410", "rv_0408"}:
            review.update(reply_status="posted", reply_by="owner", reply_text="감사해요!", reply_posted_at="2026-11-17T08:00:00+09:00")
    donna = prepared(payload, permission=True)  # 부정 리뷰 답글 대리지만 바로 답한 리뷰가 없어 H-10 단계도 건너뛴다
    steps = [donna.turn("오늘 일정 브리핑해 줘")["briefing"]["step_key"]]
    while True:
        response = donna.turn("다음")
        if response["type"] == "end":
            break
        steps.append(response["briefing"]["step_key"])
    assert steps == ["sum_reviews", "sum_resv", "detail_ask", "reviews", "staff_tasks"]


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
