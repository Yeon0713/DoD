"""시나리오 A: 처음 쓰는 날 (허락을 아직 안 물음). 문서 13장. v0.2.1 화면 포맷 (17장): 칩과 줄 이름표가 없다."""

from voice import hr, repo, width
from voice.tests.conftest import Donna


def test_a1_home(donna: Donna):
    home = donna.home()
    assert home["briefing_ready"] is True and home["headline"] == "오늘 일정 브리핑 준비했어요"
    assert "say" not in home
    rows = home["cards"][0]["rows"]
    assert [r["id"] for r in rows] == ["p_schedule", "p_reviews", "p_replies"] and all("label" not in r for r in rows)
    assert [r["value"] for r in rows] == ["행사, 경기, 단체 12명", "밤사이 리뷰 5개 읽어 둠", "좋은 리뷰 답글 3개 예약"]
    assert home["date_label"] == "11월 17일 화요일" and "suggestions" not in home
    assert home["store"] == {"id": "s001", "name": "도나네 곱창 역삼점", "logo_url": None, "open_time": "10:00", "close_time": "22:00"}
    assert home["store_status"] == {"state": "before_open", "label": "영업 전", "detail": "오전 10시에 열어요"}
    assert width.violations(home) == []


def test_scenario_a_full_flow(donna: Donna):
    a2 = donna.turn("오늘 일정 브리핑해 줘")
    assert (a2["type"], a2["intent"], a2["briefing"]) == ("answer", "briefing.start", {"step": 1, "total": 5, "step_key": "schedule"})
    assert a2["headline"] == "저녁 7시에 단체 12명이 와요"
    rows = a2["cards"][0]["rows"]
    assert [r["kind"] for r in rows] == ["event", "game", "reservation", "group_reservation"]
    assert [r["value"] for r in rows] == ["강남 페스티벌 저녁 6시", "한국시리즈 저녁 6시 반", "저녁 예약 4팀", "저녁 7시 단체 12명"]
    group = next(s for s in a2["say"] if s["focus"] == ["s_group"])
    assert group["text"] == "저녁 7시에 단체 손님 열두 분이 오세요." and group["caption"] is None
    assert "suggestions" not in a2 and a2["expects_reply"] is False

    a3 = donna.turn("다음")
    assert a3["type"] == "answer" and a3["briefing"]["step"] == 2
    counts = {i["kind"]: i["count"] for i in a3["cards"][0]["items"]}
    assert counts == {"positive": 3, "negative": 2}

    a4 = donna.turn(event="auto_next")
    # 부정 리뷰 답글 인턴: 써 둔 답글을 리뷰마다 묻는다 (허락 질문 D-10 은 없앰, 인사과 4-a)
    assert a4["type"] == "ask_action" and a4["briefing"] == {"step": 2, "total": 5, "step_key": "negative"} and a4["owner_said"] is None
    assert a4["action"]["kind"] == "batch" and a4["action"]["items"] == [{"job": "negative_reply", "ref": "rv_0412"}]
    assert [s["text"] for s in a4["say"]] == ["어젯밤 배달로 드신 손님이 배달이 늦어 음식이 식었다는 리뷰를 남기셨어요.", "써 둔 사과 답글을 올릴까요?"]
    assert a4["expects_reply"] is True and a4["cards"][0]["type"] == "review" and a4["cards"][0]["reply"]["posted_at"] is None

    yes = donna.turn("응, 올려")  # 첫 건을 올리고 다음 건을 묻는다
    assert yes["intent"] == "action.approve" and yes["type"] == "ask_action" and yes["briefing"]["step_key"] == "negative"
    assert [s["text"] for s in yes["say"]][0] == "사과 답글을 올렸어요."
    assert yes["action"]["items"] == [{"job": "negative_reply", "ref": "rv_0405"}]
    no = donna.turn("안 해")  # 둘째는 초안으로 남기고 다음 단계로
    assert no["intent"] == "action.cancel" and [s["text"] for s in no["say"]][:2] == ["네, 올리지 않을게요.", "초안은 남겨 둘게요."]
    assert {r["id"]: r["reply_status"] for r in repo.reviews("s001") if r.get("sentiment") == "negative"} == {
        "rv_0412": "posted", "rv_0405": "drafted"}
    assert [(e["job"], e["ref"], e["reaction"]) for e in hr.events("s001")] == [
        ("negative_reply", "rv_0412", "approved"), ("negative_reply", "rv_0405", "rejected")]
    a5 = no

    assert a5["type"] == "answer" and a5["briefing"] == {"step": 3, "total": 5, "step_key": "positive"}
    bars, tip = a5["cards"]
    assert [(b["label"], b["count"]) for b in bars["items"]] == [("곱창전골 국물", 9), ("친절한 응대", 6), ("넉넉한 양", 4)]
    assert tip["type"] == "tip" and tip["kind"] == "keep"
    assert a5["headline"] == "국물 맛을 좋아하세요"

    a6 = donna.turn("다음")
    assert a6["type"] == "answer" and a6["briefing"] == {"step": 3, "total": 5, "step_key": "scheduling"}
    items = a6["cards"][0]["items"]
    # P12 (test-scenarios-closed-loop.md): 주말 리뷰는 24~48시간 안 식사 피크 한 시간 전, 평일 리뷰는 토요일 오전.
    # 그날 강남 페스티벌은 시각을 바꾸지 않고 글에만 들어간다.
    assert [i["reason"]["kind"] for i in items] == ["weekend_next_peak", "weekday_to_weekend"]
    assert [(i["day_label"], i["time_label"], i["text"]) for i in items] == [
        ("화", "오전 11시", "행사 가기 전에 들르시게"), ("토", "오전 11시", "주말에 리뷰를 많이 봐요")]
    assert [i["reason"]["label"] for i in items] == ["점심 한 시간 전", "주말 점심 전"]
    assert [i["review_ids"] for i in items] == [["rv_0408"], ["rv_0409", "rv_0410"]]
    assert all("explanation" not in i for i in items)  # 말할 때만 쓰는 칸은 카드에 넣지 않는다

    a7 = donna.turn("다음")
    assert a7["type"] == "end" and a7["headline"] == "브리핑은 여기까지예요" and a7["briefing"]["step"] == 5
    assert a7["cards"][0]["title"] == "오늘 아침에 한 것"
    assert [r["value"] for r in a7["cards"][0]["rows"]] == ["좋은 리뷰 답글 예약"]  # 사장님이 "응"한 답글은 이미 아신다
    assert a7["say"][-1]["text"] == "좋은 리뷰 답글은 예약했어요."

    for response in (a2, a3, a4, yes, no, a6, a7):
        assert width.violations(response) == [], response["headline"]


def test_scheduled_replies_are_written_and_queued(donna: Donna):
    state = donna.state()
    scheduled = [r for r in state["review"] if r.get("reply_status") == "scheduled"]
    assert {r["id"] for r in scheduled} == {"rv_0408", "rv_0409", "rv_0410"}
    assert all(r["reply_text"] and r["reply_source"] == "TEMPLATE" for r in scheduled)
    assert {j["kind"] for j in state["job"] if not j["done"]} >= {"post_scheduled", "prepare_briefing"}

    # 예약한 시각이 지나면 올린다 (일요일 리뷰 → 화요일 점심 한 시간 전 11시)
    donna.clock("2026-11-17T11:00:00+09:00")
    posted = {r["id"]: r for r in donna.state()["review"] if r.get("reply_status") == "posted" and r.get("reply_by") == "donna"}
    assert list(posted) == ["rv_0408"] and posted["rv_0408"]["reply_posted_at"] == "2026-11-17T11:00:00+09:00"


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
