"""시나리오 A: 처음 쓰는 날 (허락을 아직 안 물음). 문서 13장. v0.2.1 화면 포맷 (17장): 칩과 줄 이름표가 없다."""

from voice import hr, repo, width
from voice.tests.conftest import Donna


def test_a1_home(donna: Donna):
    home = donna.home()
    assert home["briefing_ready"] is True and home["headline"] == "오늘 일정 브리핑 준비했어요"
    assert "say" not in home
    rows = home["cards"][0]["rows"]
    # H-01: 오늘 일정 → 밤사이 리뷰 → 예약 손님 요청사항 → 예약한 답글 (많아야 네 줄)
    assert [r["id"] for r in rows] == ["p_schedule", "p_reviews", "p_request", "p_replies"] and all("label" not in r for r in rows)
    assert [r["value"] for r in rows] == ["행사, 경기, 단체 12명", "밤사이 리뷰 4건 읽어 둠", "7시 손님 요청사항 받아 둠",
                                          "좋은 리뷰 답글 3건 예약"]
    assert home["date_label"] == "11월 17일 화요일" and "suggestions" not in home
    assert home["store"] == {"id": "s001", "name": "도나네 곱창 역삼점", "logo_url": None, "open_time": "10:00", "close_time": "22:00"}
    assert home["store_status"] == {"state": "before_open", "label": "영업 전", "detail": "오전 10시에 열어요"}
    assert width.violations(home) == []


def test_scenario_a_full_flow(donna: Donna):
    """v0.2.1 H: 요약 (리뷰 → 예약) → "상세 브리핑을 시작할까요?" → 리뷰 → 예약한 답글 → 아쉬운 리뷰 → 알바생 할 일 → 끝."""
    a2 = donna.turn("오늘 일정 브리핑해 줘")  # 비가 없는 날이라 요약은 도착한 리뷰부터
    assert (a2["type"], a2["intent"], a2["briefing"]) == ("answer", "briefing.start", {"step": 1, "total": 4, "step_key": "sum_reviews"})
    assert a2["headline"] == "도착한 리뷰는 4건이에요" and [s["text"] for s in a2["say"]] == ["오늘 도착한 리뷰는 네 건입니다."]
    rows = a2["cards"][0]["rows"]
    assert [r["kind"] for r in rows] == ["reviews", "event", "game", "reservation"]
    assert [r["value"] for r in rows] == ["도착한 리뷰 4건", "강남 페스티벌 저녁 6시", "한국시리즈 저녁 6시 반", "예약 5팀, 요청사항 1건"]
    assert a2["say"][0]["focus"] == ["s_reviews"] and a2["say"][0]["caption"] is None
    assert "suggestions" not in a2 and a2["expects_reply"] is False

    resv = donna.turn(event="auto_next")  # 같은 카드에서 예약 줄만 진하게 (H-04)
    assert resv["briefing"] == {"step": 1, "total": 4, "step_key": "sum_resv"} and resv["cards"] == a2["cards"]
    assert resv["headline"] == "7시 손님 요청사항이 왔어요"
    assert [s["text"] for s in resv["say"]] == ["오늘은 강남 페스티벌과 한국시리즈가 있어요.",
                                                "오늘 예약은 총 다섯 건이며, 7시 예약 손님의 요청사항이 도착했습니다."]

    ask = donna.turn(event="auto_next")  # H-05
    assert (ask["type"], ask["ask"], ask["expects_reply"]) == ("ask", {"key": "detail"}, True)
    assert ask["briefing"]["step_key"] == "detail_ask" and ask["headline"] == "상세 브리핑을 시작할까요?"

    a3 = donna.turn("응")
    assert a3["type"] == "answer" and a3["briefing"] == {"step": 3, "total": 4, "step_key": "reviews"}
    assert a3["headline"] == "리뷰 4건이 도착했습니다"
    counts = {i["kind"]: (i["count"], i["unit"]) for i in a3["cards"][0]["items"]}
    assert counts == {"positive": (3, "건"), "negative": (1, "건")}

    # 칭찬 답글 과장(이미 쓰던 가게): 묻지 않고 예약했으므로 예약한 답글을 보여 주기만 한다 (H-09, 인사과 4-b, 9-0 c).
    h09 = donna.turn(event="auto_next")
    assert h09["type"] == "answer" and h09["briefing"]["step_key"] == "positive_scheduled" and h09["expects_reply"] is False
    assert h09["headline"] == "토요일 오전 11시에\n답변을 예약해두었습니다"
    assert h09["cards"][0]["type"] == "reply_list" and [i["id"] for i in h09["cards"][0]["items"]] == ["rv_0410", "rv_0409"]
    # P12 (test-scenarios-closed-loop.md): 주말 리뷰는 24~48시간 안 식사 피크 한 시간 전, 평일 리뷰는 토요일 오전
    post_at = {r["id"]: r["reply_post_at"] for r in repo.reviews("s001") if r.get("reply_status") == "scheduled"}
    assert post_at == {"rv_0408": "2026-11-17T11:00:00+09:00", "rv_0409": "2026-11-21T11:00:00+09:00",
                       "rv_0410": "2026-11-21T11:00:00+09:00"}

    a4 = donna.turn(event="auto_next")
    # 부정 리뷰 답글 인턴: 써 둔 답글을 리뷰마다 묻는다 (허락 질문 D-10 은 없앰, 인사과 4-a)
    assert a4["type"] == "ask_action" and a4["briefing"] == {"step": 3, "total": 4, "step_key": "negative"} and a4["owner_said"] is None
    assert a4["action"]["kind"] == "batch" and a4["action"]["items"] == [{"job": "negative_reply", "ref": "rv_0412"}]
    assert [s["text"] for s in a4["say"]] == ["어젯밤 배달로 드신 손님이 배달이 늦어 음식이 식었다는 리뷰를 남기셨어요.", "써 둔 사과 답변을 올릴까요?"]
    assert a4["expects_reply"] is True and a4["cards"][0]["type"] == "review" and a4["cards"][0]["reply"]["posted_at"] is None

    yes = donna.turn("응, 올려")  # 첫 건을 올리고 다음 건을 묻는다
    assert yes["intent"] == "action.approve" and yes["type"] == "ask_action" and yes["briefing"]["step_key"] == "negative"
    assert [s["text"] for s in yes["say"]][0] == "사과 답글을 올렸어요."
    assert yes["action"]["items"] == [{"job": "negative_reply", "ref": "rv_0405"}]
    no = donna.turn("안 해")  # 둘째는 초안으로 남기고 다음 단계(알바생 할 일)로
    assert no["intent"] == "action.cancel" and [s["text"] for s in no["say"]][:2] == ["네, 올리지 않을게요.", "초안은 남겨 둘게요."]
    assert {r["id"]: r["reply_status"] for r in repo.reviews("s001") if r.get("sentiment") == "negative"} == {
        "rv_0412": "posted", "rv_0405": "drafted"}
    assert [(e["job"], e["ref"], e["reaction"]) for e in hr.events("s001")] == [
        ("negative_reply", "rv_0412", "approved"), ("negative_reply", "rv_0405", "rejected")]

    # H-11: 예약 메모의 알레르기 (규칙, agents/field_tasks.allergy_items)
    assert no["type"] == "ask_tasks" and no["briefing"] == {"step": 4, "total": 4, "step_key": "staff_tasks"}
    assert no["headline"] == "알바생 할 일에 넣을까요?"
    assert [s["text"] for s in no["say"]][2:] == ["7시 예약 손님 중 두 분이 갑각류 알레르기가 있어요.", "알바생 할 일에 넣을까요?"]
    tasks = donna.turn("응")
    assert tasks["type"] == "answer" and tasks["headline"] == "알바생 할 일에 넣었어요"
    assert tasks["briefing"]["step_key"] == "staff_tasks"  # 가만히 있으면 끝으로 넘어간다

    a7 = donna.turn(event="auto_next")
    assert a7["type"] == "end" and a7["headline"] == "오늘 브리핑은 여기까지예요" and a7["briefing"] == {"step": 4, "total": 4, "step_key": "end"}
    assert a7["cards"][0]["title"] == "오늘 아침에 한 것"
    # 여쭤보고 올린 사과 답글도 언제 올렸는지 적는다 (J-12b). 초안으로 남긴 rv_0405 는 세지 않는다
    assert [(r["value"], r["sub"]) for r in a7["cards"][0]["rows"]] == [
        ("좋은 리뷰 2건 답변", "9:00에 토요일 답변을 예약했어요"), ("아쉬운 리뷰 1건 사과 답변", "9:00에 올렸어요"),
        ("7시 손님 갑각류 알레르기", "9:00에 알바생 할 일에 넣었어요")]
    assert [s["text"] for s in a7["say"]] == ["오늘 브리핑은 여기까지예요."]

    for response in (a2, resv, ask, a3, h09, a4, yes, no, tasks, a7):
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
