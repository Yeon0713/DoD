"""시나리오 B: 허락한 다음 날. 문 닫은 뒤(22:00) 밤에 아쉬운 리뷰가 오면 30분 안에 바로 답하고, 아침 브리핑 3단계에서 알려 준다. 문서 13장."""

from voice import width
from voice.tests.conftest import Donna, baseline

NIGHT_REVIEW = {"platform": "baemin", "rating": 1, "text": "배달이 너무 늦어서 다 식어서 왔어요. 곱창은 맛있는데 아쉽네요.",
                "written_at": "2026-11-16T22:40:00+09:00", "order_channel": "delivery"}


def night_then_morning() -> tuple[Donna, str]:
    payload = baseline()
    payload["reviews"] = [r for r in payload["reviews"] if r["id"] != "rv_0412"]  # 밤 리뷰는 dev/reviews 로 넣는다
    payload["settings"] = {"negative_review_auto_reply": True}
    donna = Donna()
    donna.clock("2026-11-16T22:40:00+09:00")
    donna.fixtures(payload)
    created = donna.review(**NIGHT_REVIEW)
    assert list(created) == ["review_id"]  # B2: 리뷰가 들어와도 앱에 보내는 것은 없다 (백엔드만 안다)
    donna.clock("2026-11-17T09:00:00+09:00")
    return donna, created["review_id"]


def test_b1_auto_reply_within_30_minutes():
    donna, review_id = night_then_morning()
    review = next(r for r in donna.state()["review"] if r["id"] == review_id)
    assert review["sentiment"] == "negative" and review["topic"] == "delivery" and review["summary"] == "배달이 늦어 음식이 식었대요"
    assert review["reply_status"] == "posted" and review["reply_by"] == "donna"
    assert review["replied_in_minutes"] <= 30 and review["reply_posted_at"] == "2026-11-16T22:50:00+09:00"
    assert review["reply_text"].startswith("늦은 배달로 불편을 드려 죄송합니다")  # 에이전트를 끈 테스트라 안전 템플릿
    assert donna.home()["briefing_ready"] is True  # 09:00 에 작업 큐가 브리핑을 준비했다


def test_b3_to_b6_negative_step_and_detail():
    donna, review_id = night_then_morning()
    donna.turn("오늘 일정 브리핑해 줘")
    donna.turn("다음")
    b3 = donna.turn("다음")
    assert b3["type"] == "answer" and b3["briefing"] == {"step": 2, "total": 5, "step_key": "negative"}
    assert b3["headline"] == "10분 만에 답했어요"
    # v0.2.1 (D-11): 리뷰 원문과 실제로 단 답글을 그대로 보여 준다. 고칠 점(tip improve)은 내지 않는다
    [review_card] = b3["cards"]
    assert review_card["type"] == "review" and review_card["variant"] == "full" and review_card["id"] == review_id
    assert review_card["text"] == NIGHT_REVIEW["text"] and review_card["reply"]["by"] == "donna"
    assert review_card["reply"]["text"].startswith("늦은 배달로 불편을 드려 죄송합니다")
    assert [s["text"] for s in b3["say"]] == ["어젯밤 배달로 드신 손님이 배달이 늦어 음식이 식었다는 리뷰를 남기셨어요.",
                                             "10분 만에 사과 답글을 달았어요."]

    b4 = donna.turn("화면에 보여 줘")
    assert b4["type"] == "show_detail" and len(b4["say"]) == 1
    full = b4["cards"][0]
    assert full["variant"] == "full" and full["text"] == NIGHT_REVIEW["text"]
    assert full["reply"]["text"].startswith("늦은 배달로") and full["reply"]["posted_at"] == "2026-11-16T22:50:00+09:00"

    b5 = donna.turn("읽어 줘")
    spoken = [s["text"] for s in b5["say"]]
    assert b5["type"] == "answer" and NIGHT_REVIEW["text"] in spoken and full["reply"]["text"] in spoken

    b6 = donna.turn("돌아가기")
    assert b6["type"] == "answer" and b6["briefing"]["step_key"] == "negative" and b6["headline"] == "10분 만에 답했어요"
    assert [s["text"] for s in b6["say"]] == ["브리핑으로 돌아왔어요."]

    for response in (b3, b4, b5, b6):
        assert width.violations(response) == []


def test_no_auto_reply_without_permission_or_after_30_minutes():
    payload = baseline()
    payload["reviews"] = [r for r in payload["reviews"] if r["id"] != "rv_0412"]
    donna = Donna()
    donna.clock("2026-11-16T22:40:00+09:00")
    donna.fixtures(payload)  # 허락을 아직 안 물음
    review_id = donna.review(**NIGHT_REVIEW)["review_id"]
    donna.clock("2026-11-17T09:00:00+09:00")
    review = next(r for r in donna.state()["review"] if r["id"] == review_id)
    assert review["reply_status"] == "none"

    # 허락했어도 30분이 지난 리뷰에는 바로 답하지 않는다
    donna.settings(True)
    assert donna.run("auto_reply")["replied"] == []


def test_permission_refused_shows_draft_without_posting():
    from voice.tests.conftest import prepared

    donna = prepared(permission=False)
    donna.turn("오늘 일정 브리핑해 줘")
    donna.turn("다음")
    step3 = donna.turn("다음")
    assert step3["type"] == "answer" and step3["headline"] == "아쉬운 리뷰가 2개 있어요"
    assert step3["cards"][0]["reply"]["posted_at"] is None and step3["cards"][0]["reply"]["text"]  # 써 둔 초안 (올리지 않음)
    detail = donna.turn("화면에 보여 줘")
    assert detail["cards"][0]["reply"]["posted_at"] is None and detail["cards"][0]["reply"]["text"]
    drafted = [r for r in donna.state()["review"] if r.get("reply_status") == "drafted"]
    assert {r["id"] for r in drafted} == {"rv_0412", "rv_0405"}  # 초안만 쓰고 올리지 않는다
    assert width.violations(step3) == [] and width.violations(detail) == []
