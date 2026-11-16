"""v0.2.1 초옹장(s005) 하루: Figma 'v0.2.1 : 디자인개선' D-07 ~ D-16 과 일정·매출 탭, 도나 목소리 글.

에이전트는 꺼져 있어 답글은 안전 템플릿이다. 실제 답글은 하네스(voice_reply)가 쓴다.
"""

import json

import pytest

from voice import config, tts, width
from voice.tests.conftest import Donna

FIXTURE = config.FIXTURES / "s005_choongjang.json"


class Choongjang(Donna):
    def __init__(self):
        super().__init__()
        self.session_id = "sess_20261117_s005"

    def get(self, path: str) -> dict:
        response = self.client.get(path, params={"store_id": "s005"})
        assert response.status_code == 200, response.text
        return response.json()

    def turn(self, text: str | None = None, **kw) -> dict:
        self.number += 1
        body = {"request_id": f"req_{self.number:04d}", "store_id": "s005", "session_id": self.session_id,
                "utterance": None if text is None else {"text": text, "source": "voice", "addressed": kw.get("addressed", False)},
                "event": kw.get("event")}
        response = self.client.post("/v1/turn", json=body)
        assert response.status_code == 200, response.text
        return response.json()


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
    assert home["store_status"] == {"state": "before_open", "label": "영업 전", "detail": "오전 10시 반에 열어요"}
    assert [r["value"] for r in home["cards"][0]["rows"]] == ["단체 12명, 오후 비", "밤사이 리뷰 5개 읽어 둠", "좋은 리뷰 답글 3개 예약"]
    assert chj.client.get("/static/logos/s005.png").status_code == 200


def test_briefing_follows_figma(chj: Choongjang):
    d08 = chj.turn("오늘 일정 브리핑해 줘")
    assert d08["headline"] == "낮 12시에 단체 12명이 와요"
    assert [r["value"] for r in d08["cards"][0]["rows"]] == ["오후 2시부터 비", "저녁 예약 2팀", "낮 12시 단체 12명"]
    assert [s["text"] for s in d08["say"]] == ["오늘 일정이에요.", "낮 12시에 단체 손님 열두 분이 오세요.", "저녁 예약은 두 팀이고,",
                                              "오후 2시부터 비 소식이 있어요."]

    d09 = chj.turn(event="auto_next")
    assert d09["headline"] == "답글 기다리는 리뷰 5개"
    d10 = chj.turn(event="auto_next")
    assert d10["type"] == "ask_permission" and d10["headline"] == "제가 바로 답할까요?"

    d11 = chj.turn("응, 그렇게 해")
    assert d11["headline"] == "방금 답글을 달았어요"
    assert d11["say"][1]["text"] == "어젯밤 배달로 드신 손님이 면이 불어서 왔다는 리뷰를 남기셨어요."
    assert d11["cards"][0]["text"] == "면이 불어서 왔어요." and d11["cards"][0]["reply"]["by"] == "donna"

    d12 = chj.turn("다음")
    assert d12["headline"] == "들깨 국물을 좋아하세요"
    assert [(b["label"], b["count"]) for b in d12["cards"][0]["items"]] == [("고소한 들깨 국물", 9), ("쫀득한 옹심이", 6), ("넉넉한 양", 4)]
    assert d12["cards"][1]["text"] == "들깨는 지금처럼 그날 아침에 갈아 주세요"

    d13 = chj.turn("다음")
    items = d13["cards"][0]["items"]
    assert [(i["day_label"], i["time_label"], i["reason"]["kind"], i["text"]) for i in items] == [
        ("목", "아침 8시", "weather", "비 오는 날 옹심이 권하기"),
        ("금", "오전 10시 반", "lunch", "점심 메뉴 고를 때 보시게"),
        ("토", "오전 11시", "weekend", "주말에 리뷰를 많이 봐요")]
    # 비 오는 날 또 오겠다는 리뷰는 비 오는 날에, 점심 리뷰는 점심 때에
    assert [i["review_ids"] for i in items] == [["rv_0401"], ["rv_0405"], ["rv_0409"]]

    d16 = chj.turn("다음")
    assert d16["type"] == "end" and d16["cards"][0]["title"] == "오늘 아침에 한 것"
    for response in (d08, d09, d10, d11, d12, d13, d16):
        assert width.violations(response) == [], (response["headline"], width.violations(response))
        assert "suggestions" not in response


def test_week_tab_shows_facts_and_what_was_done(chj: Choongjang):
    chj.turn("오늘 일정 브리핑해 줘")
    for _ in range(5):
        chj.turn("다음")
    week = chj.get("/v1/week")
    today = next(d for d in week["days"] if d["is_today"])
    assert today["title"] == "단체 예약이 있어요" and [p["kind"] for p in today["plans"]] == ["group_reservation", "weather"]
    assert "오늘 일정 브리핑을 들었어요" in [d["text"] for d in today["done"]]
    assert len(week["days"]) == 42 and [s["day_label"] for s in week["scheduled"]] == ["목", "금", "토"]
    assert week["past"][0]["label"] == "어제" and week["past"][1]["label"] == "지난주"


def test_sales_and_notices(chj: Choongjang):
    sales = chj.get("/v1/sales")
    assert sales["primary"]["label"] == "어제" and sales["primary"]["amount_label"] == "128만 원"  # 문 열기 전이라 어제
    assert sales["top_menus"]["items"][0]["label"] == "들깨옹심이메밀칼국수"
    assert chj.get("/v1/notices") == {"notices": []}
    settings = chj.get("/v1/settings")
    assert settings["store"]["name"] == "초옹장" and settings["open_time_label"] == "오전 10시 반"


def test_tts_is_off_in_tests_and_app_falls_back(chj: Choongjang):
    response = chj.client.get("/v1/tts", params={"text": "오늘 일정이에요."})
    assert response.status_code == 204  # 만든 목소리가 없으면 앱이 기기 목소리로 읽는다
    assert chj.client.get("/v1/tts/status").json()["available"] is False


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
