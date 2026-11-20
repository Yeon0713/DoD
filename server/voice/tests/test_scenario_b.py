"""시나리오 B: 부정 리뷰 답글이 대리인 가게(예전: 허락한 다음 날). 문 닫은 뒤(22:00) 밤에 아쉬운 리뷰가 오면 30분 안에 바로 답하고,
아침 브리핑 3단계에서 알려 준다. 문서 13장. 인턴·사원은 아침에 "올릴까요?"로 묻는다 (인사과 4-a)."""

from voice import width
from voice.tests.conftest import Donna, baseline

NIGHT_REVIEW = {"platform": "baemin", "rating": 1, "text": "배달이 너무 늦어서 다 식어서 왔어요. 곱창은 맛있는데 아쉽네요.",
                "written_at": "2026-11-16T22:40:00+09:00", "order_channel": "delivery"}


def night_then_morning() -> tuple[Donna, str]:
    payload = baseline()
    payload["reviews"] = [r for r in payload["reviews"] if r["id"] != "rv_0412"]  # 밤 리뷰는 dev/reviews 로 넣는다
    payload["hr"] = {**payload["hr"], "negative_reply": "assistant"}  # 묻지 않고 답한다
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


def test_b3_to_b6_done_report_and_detail():
    """대리가 밤사이 올린 답글은 아쉬운 리뷰 단계가 아니라 사후 보고 단계(done_report, 게이지 1)에서 알린다 (인사과 5단계)."""
    donna, review_id = night_then_morning()
    donna.turn("오늘 일정 브리핑해 줘")
    b3 = donna.turn("다음")
    assert b3["type"] == "answer" and b3["briefing"] == {"step": 1, "total": 5, "step_key": "done_report"}
    assert b3["headline"] == "제가 처리한 것이에요"
    assert [s["text"] for s in b3["say"]] == ["제가 알아서 처리한 게 있어요.", "아쉬운 리뷰 한 개에 사과 답글을 올렸어요.",
                                             "배달이 늦어 음식이 식었다는 리뷰에 단 답글이에요.",
                                             "되돌릴 게 있으면 '그 답글 지워'처럼 말씀해 주세요."]
    assert [(r["label"], r["value"]) for r in b3["cards"][0]["rows"]] == [("아쉬운 리뷰 답글", "1건")]

    b4 = donna.turn("화면에 보여 줘")
    assert b4["type"] == "show_detail" and b4["cards"][0]["id"] == review_id
    assert b4["cards"][0]["reply"]["text"].startswith("늦은 배달로") and b4["cards"][0]["reply"]["posted_at"] == "2026-11-16T22:50:00+09:00"
    b5 = donna.turn("읽어 줘")
    assert [s["text"] for s in b5["say"]] == ["첫 번째, 배달이 늦어 음식이 식었다는 리뷰에 단 답글이에요."]
    b6 = donna.turn("돌아가기")
    assert b6["briefing"]["step_key"] == "done_report" and [s["text"] for s in b6["say"]] == ["브리핑으로 돌아왔어요."]
    after = donna.turn("다음")
    assert after["briefing"]["step_key"] == "reviews"  # 아쉬운 리뷰 단계는 대리면 없다 (밤 리뷰는 이미 올렸다)
    for response in (b3, b4, b5, b6):
        assert width.violations(response) == []


def test_no_auto_reply_without_permission_or_after_30_minutes():
    payload = baseline()
    payload["reviews"] = [r for r in payload["reviews"] if r["id"] != "rv_0412"]
    donna = Donna()
    donna.clock("2026-11-16T22:40:00+09:00")
    donna.fixtures(payload)  # 부정 리뷰 답글 인턴
    review_id = donna.review(**NIGHT_REVIEW)["review_id"]
    donna.clock("2026-11-17T09:00:00+09:00")
    review = next(r for r in donna.state()["review"] if r["id"] == review_id)
    assert review["reply_status"] == "none"

    # 대리가 되어도 30분이 지난 리뷰에는 바로 답하지 않는다
    donna.settings(True)
    assert donna.run("auto_reply")["replied"] == []


def test_staff_rank_asks_negative_replies_together():
    """부정 리뷰 답글 사원: 밤사이 아쉬운 리뷰를 묶어서 한 번에 묻는다. "두 번째는 빼고 올려"면 그것만 초안으로 (인사과 4-a)."""
    from voice import hr
    from voice.tests.conftest import prepared

    payload = baseline()
    payload["hr"] = {**payload["hr"], "negative_reply": "staff"}
    donna = prepared(payload)
    donna.turn("오늘 일정 브리핑해 줘")
    donna.turn("다음")
    step3 = donna.turn("다음")
    assert step3["type"] == "ask_action" and step3["headline"] == "사과 답글 올릴까요?" and step3["action"]["mode"] == "batch"
    assert [s["text"] for s in step3["say"]] == ["아쉬운 리뷰가 두 개 있어요.", "첫째, 배달이 늦어 음식이 식었다는 리뷰예요.",
                                                "둘째, 배달이 늦었다는 리뷰예요.", "써 둔 사과 답글을 올릴까요?"]
    assert [i["title"] for i in step3["cards"][0]["items"]] == ["1. 배달이 늦어 음식이 식었대요", "2. 배달이 늦었대요"]
    done = donna.turn("두 번째는 빼고 올려")
    assert done["intent"] == "action.approve" and done["say"][0]["text"] == "사과 답글을 올렸어요."
    assert done["briefing"]["step_key"] == "positive"  # 정하면 다음 단계로
    status = {r["id"]: r["reply_status"] for r in donna.state()["review"] if r.get("sentiment") == "negative"}
    assert status == {"rv_0412": "posted", "rv_0405": "drafted"}
    assert [(e["ref"], e["reaction"]) for e in hr.events("s001")] == [("rv_0405", "rejected"), ("rv_0412", "approved")]
    assert width.violations(step3) == [] and width.violations(done) == []
