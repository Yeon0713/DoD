"""v0.2.1 매출 탭(Figma G-04)과 설정 탭(G-05 ~ G-08): 초옹장(s005) 11월 17일 화요일.

매출: 오늘(문 열기 전에는 어제) ↔ 지난주 같은 요일, 이번 주·이번 달 지금까지, 도나 답글을 받고 다시 온 손님, 이번 달 메뉴.
설정: 브리핑 알림(기본 문 열기 1시간 전, 사장님이 고름), 요일별 장사 시간(네이버 시간으로 되돌릴 수 있게).
"""

from voice import repo
from voice.tests.test_v021_choongjang import Choongjang, chj  # noqa: F401  (픽스처)


def patch(chj: Choongjang, **body) -> dict:
    response = chj.client.patch("/v1/settings", json={"store_id": "s005", **body})
    assert response.status_code == 200, response.text
    return response.json()


def test_sales_before_open_shows_yesterday_month_and_revisits(chj: Choongjang):
    sales = chj.get("/v1/sales")  # 09:02, 문 열기 전
    primary = sales["primary"]
    assert (primary["label"], primary["amount_label"], primary["compare_amount_label"]) == ("어제", "128만 원", "152만 원")
    assert primary["direction"] == "down" and primary["short_text"] == "지난주보다 24만 원 적어요"
    month = sales["month"]  # 11월 1 ~ 16일 ↔ 10월 1 ~ 16일
    assert (month["amount_label"], month["diff_text"], month["direction"]) == ("2,446만 원", "95만 원 많아요", "up")
    revisits = sales["revisits"]
    assert (revisits["count_label"], revisits["last_week_label"]) == ("1명", "지난주에는 3명")
    latest = revisits["latest"]
    assert latest["came_back_label"] == "11월 16일 배달로 다시 주문했어요"
    assert latest["review"] == {"rating": 5, "text": "추운 날 옹심이 한 그릇 하니까 몸이 녹네요.", "date_label": "11월 12일 리뷰"}
    assert sales["top_menus_month"]["items"][0] == {"id": "m_1", "label": "들깨옹심이메밀칼국수", "count": 461}


def test_sales_while_open_compares_same_time(chj: Choongjang):
    chj.clock("2026-11-17T14:00:00+09:00")
    sales = chj.get("/v1/sales")
    primary = sales["primary"]
    assert (primary["label"], primary["amount_label"], primary["compare_label"]) == ("오늘 지금까지", "42만 원", "지난주 화요일 이맘때")
    assert primary["short_text"] == "지난주보다 5만 원 많아요" and primary["compare_amount"] == 372000
    week = sales["week"]  # 월 128.4 + 화 41.8 ↔ 지난주 월 152.2 + 화 이맘때 37.2
    assert (week["total_label"], week["diff_text"]) == ("170만 원", "19만 원 적어요")
    assert sales["month"]["amount_label"] == "2,487만 원" and sales["month"]["direction"] == "up"


def test_revisits_count_only_until_now(chj: Choongjang):
    chj.clock("2026-11-22T20:00:00+09:00")
    revisits = chj.get("/v1/sales")["revisits"]
    assert revisits["count_label"] == "4명"
    assert revisits["latest"]["came_back_label"] == "11월 22일 배달로 다시 주문했어요"


def test_briefing_notify_defaults_to_an_hour_before_open_and_owner_can_change(chj: Choongjang):
    settings = chj.get("/v1/settings")
    notify = settings["briefing_notify"]
    assert (notify["on"], notify["time"], notify["time_label"], notify["is_default"]) == (True, "09:30", "오전 9시 30분", True)
    assert [(o["time"], o["sub"], o["is_default"]) for o in notify["options"]] == [
        ("08:30", "문 열기 2시간 전", False), ("09:00", "문 열기 1시간 30분 전", False),
        ("09:30", "문 열기 1시간 전", True), ("10:00", "문 열기 30분 전", False)]

    changed = patch(chj, briefing_notify={"time": "08:30"})
    assert changed["briefing_notify"]["time_label"] == "오전 8시 30분" and not changed["briefing_notify"]["is_default"]
    assert "negative_review_auto_reply" not in changed  # 없앤 설정 (인사과 4-a)
    ignored = patch(chj, negative_review_auto_reply=True)  # 옛 앱이 보내도 무시한다
    assert "negative_review_auto_reply" not in ignored and "negative_review_auto_reply" not in repo.settings("s005")
    jobs = [j for j in repo.all_of("job", "s005") if j["kind"] == "prepare_briefing" and not j["done"]]
    assert [j["due_at"] for j in jobs] == ["2026-11-18T08:30:00+09:00"]  # 알림 때 이미 준비돼 있게

    assert patch(chj, briefing_notify={"on": False})["briefing_notify"]["on"] is False
    back = patch(chj, briefing_notify={"on": True, "time": None})["briefing_notify"]
    assert (back["on"], back["time"], back["is_default"]) == (True, "09:30", True)


def test_owner_edits_hours_per_weekday(chj: Choongjang):
    days = [{"open": "10:30", "close": "20:30"} for _ in range(5)]
    days += [{"open": "11:00", "close": "21:00"}, {"closed": True, "open": "10:30", "close": "20:30"}]
    settings = patch(chj, hours={"days": days})
    assert settings["hours"]["summary_label"] == "요일마다 달라요"
    assert [d["closed"] for d in settings["hours"]["days"]] == [False] * 6 + [True]
    assert {(d["open"], d["close"]) for d in settings["hours"]["naver_days"]} == {("10:30", "20:30")}  # 되돌릴 네이버 시간

    chj.clock("2026-11-22T09:00:00+09:00")  # 일요일
    assert chj.get("/v1/home")["store_status"] == {"state": "closed", "label": "쉬는 날", "detail": "내일 오전 10시 30분에 열어요"}  # 화면 글이라 숫자로 (Figma v0.2.1 H)
    chj.clock("2026-11-21T10:45:00+09:00")  # 토요일은 11시에 연다
    assert chj.get("/v1/home")["store_status"]["state"] == "before_open"


def test_bad_hours_are_refused(chj: Choongjang):
    days = [{"open": "10:30", "close": "10:30"}] * 7  # 닫는 시각이 이르면 자정 넘김이라 받는다 (V7). 같으면 거절
    response = chj.client.patch("/v1/settings", json={"store_id": "s005", "hours": {"days": days}})
    error = response.json()["error"]  # 다른 오류와 같은 모양 {"error": {"code", "message"}} (2026-11-22 버그 V8)
    assert response.status_code == 400 and error["code"] == "bad_hours" and error["message"]
    assert chj.get("/v1/settings")["hours"]["summary_label"] == "10:30 ~ 20:30"
