"""v0.2.1 초옹장(s005) 하루: Figma 'v0.2.1 : 디자인개선' D-07 ~ D-16 과 일정·매출 탭, 도나 목소리 글.

에이전트는 꺼져 있어 답글은 안전 템플릿이다. 실제 답글은 하네스(voice_reply)가 쓴다.
"""

import json

import pytest

from voice import config, repo, tts, width
from voice.tests.conftest import Choongjang

FIXTURE = config.FIXTURES / "s005_choongjang.json"


@pytest.fixture
def chj() -> Choongjang:
    donna = Choongjang()
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    donna.clock(payload["demo"]["now"])
    assert donna.client.post("/v1/dev/fixtures", json={"fixture": "s005_choongjang"}).json()["store_id"] == "s005"
    donna.client.post("/v1/dev/run", json={"store_id": "s005", "job": "prepare_briefing"})
    return donna


def test_home_header_and_status(chj: Choongjang):
    home = chj.get("/v1/home")
    assert home["store"]["name"] == "초옹장" and home["store"]["logo_url"] == "/static/logos/s005.png"
    assert home["store_status"] == {"state": "before_open", "label": "영업 전", "detail": "오전 10시 30분에 열어요"}  # 화면 글은 숫자로
    assert [r["value"] for r in home["cards"][0]["rows"]] == ["오늘 비, 단체 12명", "밤사이 리뷰 3건 읽어 둠", "12시 손님 요청사항 받아 둠",
                                                              "좋은 리뷰 답글 3건 써 둠"]  # H-01
    assert chj.client.get("/static/logos/s005.png").status_code == 200


def test_briefing_follows_figma(chj: Choongjang):
    """Figma v0.2.1 H '새 오늘 일정 브리핑': 요약 세 줄 (H-02 ~ H-04) → 허락 (H-05) → 리뷰 (H-08) → 답글 → 알바생 할 일 → 끝."""
    h02 = chj.turn("오늘 일정 브리핑해 줘")
    assert h02["headline"] == "오후 2시부터 비가 와요" and h02["briefing"] == {"step": 1, "total": 4, "step_key": "sum_weather"}
    assert [r["value"] for r in h02["cards"][0]["rows"]] == ["오후 2시부터 비", "도착한 리뷰 3건", "예약 3팀, 요청사항 2건"]
    assert [(s["text"], s["focus"]) for s in h02["say"]] == [("오늘은 오후 2시부터 비 소식이 있습니다.", ["s_rain"])]
    # 같은 카드를 두고 지금 말하는 줄만 진하게 (focus) 바꾼다
    h03 = chj.turn(event="auto_next")
    assert h03["headline"] == "도착한 리뷰는 3건이에요" and h03["cards"] == h02["cards"]
    assert [(s["text"], s["focus"]) for s in h03["say"]] == [("오늘 도착한 리뷰는 세 건입니다.", ["s_reviews"])]
    h04 = chj.turn(event="auto_next")
    assert h04["headline"] == "12시 손님 요청사항이 왔어요" and h04["cards"] == h02["cards"]
    assert [(s["text"], s["focus"]) for s in h04["say"]] == [("오늘 예약은 총 세 건이며, 12시 예약 손님의 요청사항이 도착했습니다.", ["s_resv"])]
    h05 = chj.turn(event="auto_next")
    assert (h05["type"], h05["headline"], h05["ask"], h05["expects_reply"]) == ("ask", "상세 브리핑을 시작할까요?", {"key": "detail"}, True)

    h08 = chj.turn("응")
    assert h08["briefing"] == {"step": 3, "total": 4, "step_key": "reviews"} and h08["headline"] == "리뷰 3건이 도착했습니다"
    assert [(i["label"], i["count"], i["unit"]) for i in h08["cards"][0]["items"]] == [("좋은 리뷰", 1, "건"), ("아쉬운 리뷰", 2, "건")]

    d13 = chj.turn(event="auto_next")
    # 인사과 4-b: 칭찬 답글 사원이라 써 둔 답글을 묶어서 "이렇게 예약할까요?"로 묻는다 (대리·과장이면 H-09 로 보여 주기만).
    # P10 때는 그대로: 일요일 리뷰 둘은 화요일 점심 한 시간 전(11시)에, 월요일 리뷰는 토요일 오전 11시에
    assert d13["type"] == "ask_action" and d13["headline"] == "답글 예약할까요?" and d13["action"]["mode"] == "batch"
    assert d13["briefing"]["step_key"] == "scheduling"
    assert [s["text"] for s in d13["say"]] == [
        "좋은 리뷰 답글이 세 개 있어요.", "첫째, 화요일 오전 11시에 올릴 답글이에요.", "둘째, 화요일 오전 11시에 올릴 답글이에요.",
        "셋째, 토요일 오전 11시에 올릴 답글이에요.", "이렇게 예약할까요?"]
    assert [i["ref"] for i in d13["action"]["items"]] == ["rv_0405", "rv_0401", "rv_0409"]
    d14 = chj.turn("두 번째는 빼고 예약해")
    assert d14["intent"] == "action.approve" and d14["say"][0]["text"] == "답글 2개를 예약했어요."
    status = {r["id"]: r["reply_status"] for r in repo.reviews("s005") if r["id"] in ("rv_0401", "rv_0405", "rv_0409")}
    assert status == {"rv_0401": "drafted", "rv_0405": "scheduled", "rv_0409": "scheduled"}

    d10 = d14  # 정하면 다음 단계(아쉬운 리뷰)로 이어 간다
    # 인사과 4-a: 허락 질문(D-10 "제가 바로 답할까요?")을 없앴다. 부정 리뷰 답글 인턴이라 써 둔 답글을 리뷰마다 묻는다
    assert d10["type"] == "ask_action" and d10["headline"] == "사과 답변을 올릴까요?" and d10["action"]["mode"] == "each"
    assert [s["text"] for s in d10["say"]][1:] == ["어젯밤 배달로 드신 손님이 면이 불어서 왔다는 리뷰를 남기셨어요.", "써 둔 사과 답변을 올릴까요?"]
    assert d10["cards"][0]["text"] == "면이 불어서 왔어요." and d10["cards"][0]["reply"]["posted_at"] is None

    d11 = chj.turn("응, 그렇게 해")
    assert d11["say"][0]["text"] == "사과 답글을 올렸어요." and d11["cards"][0]["text"] == "옹심이가 조금 퍼져 있었어요."
    assert d11["say"][-1]["text"] == "써 둔 사과 답변을 올릴까요?"

    # 2026-11-20: 알바생 할 일로 넣을지 묻는다 (jobs/staff_tasks.py). 예약 메모의 알레르기(규칙)가 먼저,
    # 밤사이 아쉬운 리뷰의 교정 카드가 다음 (퍼진 옹심이 리뷰도 같은 카드라 하나로 묶었다)
    d15 = chj.turn("응, 올려")
    assert d15["say"][0]["text"] == "사과 답글을 올렸어요."
    assert d15["type"] == "ask_tasks" and d15["briefing"]["step_key"] == "staff_tasks" and d15["expects_reply"] is True
    assert [s["text"] for s in d15["say"]][1:] == [
        "알바생 할 일로 넣을 게 두 개 있어요.", "첫째, 12시 손님 땅콩 알레르기. 예약 메모에 '땅콩 알레르기 손님 1명 있어요'라고 있어요.",
        "둘째, 배달 칼국수 면·국물 따로 담기. 어젯밤 면이 불어서 왔다는 리뷰 때문이에요.", "넣을까요?"]
    assert [i["title"] for i in d15["cards"][0]["items"]] == ["1. 12시 손님 땅콩 알레르기", "2. 배달 칼국수 면·국물 따로 담기"]
    d16 = chj.turn("응, 넣어")
    assert d16["type"] == "answer" and d16["briefing"]["step_key"] == "staff_tasks"  # 가만히 있으면 끝으로 넘어간다
    d17 = chj.turn(event="auto_next")
    assert d17["type"] == "end" and d17["cards"][0]["title"] == "오늘 아침에 한 것"
    assert [r["value"] for r in d17["cards"][0]["rows"]] == ["좋은 리뷰 1건 답변", "아쉬운 리뷰 2건 사과 답변", "12시 손님 땅콩 알레르기",
                                                             "알바생 할 일"]  # 긴 제목은 줄 한도 안으로
    assert [r["sub"] for r in d17["cards"][0]["rows"]][1:3] == ["9:02에 올렸어요", "9:02에 알바생 할 일에 넣었어요"]
    for response in (h02, h03, h04, h05, h08, d13, d14, d11, d15, d16, d17):
        assert width.violations(response) == [], (response["headline"], width.violations(response))
        assert "suggestions" not in response


def test_week_tab_shows_facts_and_what_was_done(chj: Choongjang):
    response = chj.turn("오늘 일정 브리핑해 줘")
    for _ in range(8):  # 마지막은 알바생 할 일 묻기 (2026-11-20)
        if (response["briefing"] or {}).get("step_key") == "scheduling":
            response = chj.turn("응, 예약해")  # 칭찬 답글 사원: 예약할까요? (인사과 4-b)
        response = chj.turn("다음")
    week = chj.get("/v1/week")
    today = next(d for d in week["days"] if d["is_today"])
    assert today["title"] == "단체 예약이 있어요" and [p["kind"] for p in today["plans"]] == ["group_reservation", "weather"]
    assert "오늘 일정 브리핑을 들었어요" in [d["text"] for d in today["done"]]
    assert len(week["days"]) == 42 and [s["day_label"] for s in week["scheduled"]] == ["화", "토"]  # P11
    assert week["past"][0]["label"] == "어제" and week["past"][1]["label"] == "지난주"


def test_sales_and_notices(chj: Choongjang):
    sales = chj.get("/v1/sales")
    assert sales["primary"]["label"] == "어제" and sales["primary"]["amount_label"] == "128만 원"  # 문 열기 전이라 어제
    assert sales["top_menus"]["items"][0]["label"] == "들깨옹심이메밀칼국수"
    assert chj.get("/v1/notices") == {"notices": []}
    settings = chj.get("/v1/settings")
    assert settings["store"]["name"] == "초옹장" and settings["open_time_label"] == "오전 10시 30분"


def test_disabled_tts_returns_no_audio(chj: Choongjang):
    response = chj.client.get("/v1/tts", params={"text": "오늘 일정이에요."})
    assert response.status_code == 204
    assert chj.client.get("/v1/tts/status").json()["available"] is False


def test_live_tts_uses_ara_pro_and_synthesizes_once(chj: Choongjang, monkeypatch):
    """같은 문장은 서버가 한 번만 합성해 기억해 둔다 (tts._cache). 앱(브라우저)에는 여전히 캐시하지 말라고 한다 (no-store)."""
    import httpx

    calls = []

    def post(url, *, headers, data, timeout):
        calls.append(data)
        assert headers["X-NCP-APIGW-API-KEY-ID"] == "test-id"
        assert headers["X-NCP-APIGW-API-KEY"] == "test-secret"
        return httpx.Response(200, content=b"audio", request=httpx.Request("POST", url))

    monkeypatch.setattr(tts, "ENABLED", True)
    monkeypatch.setattr(tts.settings, "clova_voice_client_id", "test-id")
    monkeypatch.setattr(tts.settings, "clova_voice_client_secret", "test-secret")
    monkeypatch.setattr(tts.httpx, "post", post)
    for _ in range(2):
        res = chj.client.get("/v1/tts", params={"text": "12시에 와요."})
        assert res.status_code == 200 and res.content == b"audio"
        assert res.headers["cache-control"] == "no-store"
    assert calls == [dict(speaker="vara", speed=-2, alpha=1, pitch=-1, emotion=0,
                          format="wav", text="열두 시에 와요.", **{"emotion-strength": 0})]  # 두 번째는 기억해 둔 것


@pytest.mark.parametrize("text, spoken", [
    ("낮 12시에 단체 12명이 와요", "낮 열두 시에 단체 열두 명이 와요"),
    ("오후 2시부터 비 소식이 있어요.", "오후 두 시부터 비 소식이 있어요."),
    ("앞으로는 제가 30분 안에 사과 답글을 달고,", "앞으로는 제가 삼십분 안에 사과 답글을 달고,"),
    ("어제 128만 원 팔았어요.", "어제 백이십팔만 원 팔았어요."),
    ("11월 17일 화요일", "십일월 십칠일 화요일"),
    ("저녁 예약은 두 팀이고,", "저녁 예약은 두 팀이고,"),
    ("오전 10시 반", "오전 열 시 반"),
])
def test_tts_reads_numbers_as_spoken(text, spoken):
    assert tts.spoken(text) == spoken
