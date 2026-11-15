"""시나리오 A: 처음 쓰는 날 (허락을 아직 안 물음). 문서 13장."""

from voice import repo, width
from voice.tests.conftest import Donna


def test_a1_home(donna: Donna):
    home = donna.home()
    assert home["briefing_ready"] is True and home["headline"] == "오늘 일정 브리핑 준비했어요"
    assert "say" not in home
    assert [r["id"] for r in home["cards"][0]["rows"]] == ["p_schedule", "p_reviews", "p_replies"]
    assert home["cards"][0]["rows"][1]["value"] == "5개 읽고 나눠 놨어요" and home["date_label"] == "11월 17일 화요일"
    assert width.violations(home) == []


def test_scenario_a_full_flow(donna: Donna):
    a2 = donna.turn("오늘 일정 브리핑해 줘")
    assert (a2["type"], a2["intent"], a2["briefing"]) == ("answer", "briefing.start", {"step": 1, "total": 5, "step_key": "schedule"})
    assert a2["headline"] == "오늘은 저녁이 바빠요"
    rows = a2["cards"][0]["rows"]
    assert [r["kind"] for r in rows] == ["event", "game", "reservation", "group_reservation"]
    assert [r["value"] for r in rows] == ["강남 페스티벌 저녁 6시", "한국시리즈 저녁 6시 30분", "저녁에 네 팀", "저녁 7시, 열두 분"]
    assert a2["say"][-1]["focus"] == ["s_group"] and a2["say"][-1]["text"] == "저녁 7시에는 단체 손님 열두 분이 오세요."
    assert a2["suggestions"] == ["다시 말해 줘", "다음"] and a2["expects_reply"] is False

    a3 = donna.turn("다음")
    assert a3["type"] == "answer" and a3["briefing"]["step"] == 2
    counts = {i["kind"]: i["count"] for i in a3["cards"][0]["items"]}
    assert counts == {"positive": 3, "negative": 2}

    a4 = donna.turn(event="auto_next")
    assert a4["type"] == "ask_permission" and a4["briefing"]["step"] == 3 and a4["owner_said"] is None
    assert a4["permission"] == {"key": "negative_review_auto_reply"} and a4["expects_reply"] is True
    assert a4["suggestions"] == ["응, 그렇게 해", "아니, 내가 볼게"]

    a5 = donna.turn("응 그렇게 해")
    assert a5["intent"] == "permission.yes" and a5["owner_said"] == "응, 그렇게 해"
    assert repo.settings("s001")["negative_review_auto_reply"] is True
    assert a5["type"] == "answer" and a5["briefing"]["step"] == 4
    bars, tip = a5["cards"]
    assert [(b["label"], b["count"]) for b in bars["items"]] == [("곱창전골 국물", 9), ("친절한 응대", 6), ("넉넉한 양", 4)]
    assert tip["type"] == "tip" and tip["kind"] == "keep"
    assert a5["headline"] == "국물 맛을 좋아하세요"

    a6 = donna.turn("다음")
    assert a6["type"] == "answer" and a6["briefing"]["step"] == 5
    items = a6["cards"][0]["items"]
    assert [i["reason"]["kind"] for i in items] == ["weather", "game", "weekend"]
    assert [(i["day_label"], i["time_label"], i["text"]) for i in items] == [
        ("목", "아침 8시", "비 오는 날 전골 권하기"), ("금", "오후 5시", "경기 보기 전에 들르시게"), ("토", "오전 11시", "주말에 리뷰를 많이 봐요")]
    assert [i["reason"]["label"] for i in items] == ["비 소식", "한국시리즈", "주말"]
    assert all("explanation" not in i for i in items)  # 말할 때만 쓰는 칸은 카드에 넣지 않는다

    a7 = donna.turn("다음")
    assert a7["type"] == "end" and a7["headline"] == "브리핑은 여기까지예요"
    assert {r["kind"] for r in a7["cards"][0]["rows"]} == {"done"}
    assert a7["suggestions"] == ["처음부터 다시", "리뷰 보여 줘"]

    for response in (a2, a3, a4, a5, a6, a7):
        assert width.violations(response) == [], response["headline"]


def test_scheduled_replies_are_written_and_queued(donna: Donna):
    state = donna.state()
    scheduled = [r for r in state["review"] if r.get("reply_status") == "scheduled"]
    assert {r["id"] for r in scheduled} == {"rv_0408", "rv_0409", "rv_0410"}
    assert all(r["reply_text"] and r["reply_source"] == "TEMPLATE" for r in scheduled)
    assert {j["kind"] for j in state["job"] if not j["done"]} >= {"post_scheduled", "prepare_briefing"}

    # 예약한 시각이 지나면 올린다 (목요일 아침 8시 답글)
    donna.clock("2026-11-19T08:00:00+09:00")
    posted = {r["id"]: r for r in donna.state()["review"] if r.get("reply_status") == "posted" and r.get("reply_by") == "donna"}
    assert list(posted) == ["rv_0408"] and posted["rv_0408"]["reply_posted_at"] == "2026-11-19T08:00:00+09:00"


def test_home_before_preparation():
    donna = Donna()
    donna.clock("2026-11-17T08:00:00+09:00")
    donna.fixtures()
    home = donna.home()
    assert home["briefing_ready"] is False and home["headline"] == "아직 준비하고 있어요" and home["cards"] == []
    not_ready = donna.turn("오늘 일정 브리핑해 줘")
    assert not_ready["type"] == "answer" and not_ready["headline"] == "아직 준비하고 있어요"
    # 출근 한 시간 전(09:00)이 되면 작업 큐가 준비한다
    donna.clock("2026-11-17T09:00:00+09:00")
    assert donna.home()["briefing_ready"] is True


def test_unknown_store():
    donna = Donna()
    assert donna.client.get("/v1/home", params={"store_id": "nope"}).status_code == 404
    response = donna.client.post("/v1/turn", json={"request_id": "x", "store_id": "nope", "utterance": {"text": "브리핑"}})
    assert response.status_code == 404 and response.json() == {"error": "store_not_found"}
