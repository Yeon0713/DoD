"""시험 주간 데이터(db/test_scenarios/s005.json)와 시험 날짜(app/modules/dev_tools/scenario_week.py)."""

import datetime as dt

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.seoul_time import SEOUL, clock_shift, now_seoul, set_clock_shift
from app.data_pipeline import read_store_db, store_snapshot_cache, test_scenario
from app.main import create_app
from app.modules.dev_tools import scenario_week

AT = lambda *a: dt.datetime(*a, tzinfo=SEOUL)  # noqa: E731


def test_scenario_rows_are_layered_on_store_db():
    """팀 목업 파일은 그대로 두고, 읽을 때 시험 행이 더해진다."""
    until = AT(2026, 10, 12)
    weather = {w["date"]: w for w in read_store_db.read_weather("s005")}
    assert float(weather[dt.date(2026, 10, 8)]["temp_max"]) == 9.0  # 시험 날씨
    assert float(weather[dt.date(2026, 10, 12)]["temp_max"]) == 17.6  # 그 밖의 날은 목업 날씨
    assert "남양 가을 축제" in [e["name"] for e in read_store_db.read_events("s005")]
    assert "남양 가을 축제" not in [e["name"] for e in read_store_db.read_events()]  # 다른 가게에는 안 보인다
    orders = read_store_db.read_orders("s005", until, since=AT(2026, 10, 10))
    assert any(o["order_id"] >= 9_000_001 for o in orders) and orders == sorted(orders, key=lambda o: o["ordered_at"])
    items = read_store_db.read_order_items("s005", until, since=AT(2026, 10, 10))
    assert {i["order_id"] for i in items} >= {o["order_id"] for o in orders if o["order_id"] >= 9_000_001}
    reviews = {r["review_id"]: r for r in read_store_db.read_reviews("s005", until)}
    assert reviews[900001]["order_channel"] == "delivery" and reviews[900001]["customer_key"] == "c5_0104"  # 가게 파일 주문과 이어짐
    assert reviews[900004]["content"].startswith("옹심이가 덜 익었고")
    assert 900002 not in {r["review_id"] for r in read_store_db.read_reviews("s005", AT(2026, 10, 5, 12))}  # 쓰기 전에는 없다
    assert read_store_db.read_weather("s001") == read_store_db.read_weather(None)  # 시험 데이터 없는 가게는 그대로


def test_week_has_every_kind_of_task():
    """10/5~10/11 알림 시각마다 오는 할 일에 답글, 메뉴판, 포스터, 같은 불만 점검, 단골 재주문 인사, 주간 미리보기가 모두 있다."""
    week = scenario_week.week_stops("s005")
    assert (week["start"], week["end"], len(week["stops"])) == ("2026-10-05", "2026-10-11", 21)
    by_time = {(s["day"], s["time"]): s["tasks"] for s in week["stops"]}
    assert by_time[("10/5(월)", "10:00")] == ["이번 주 미리보기 알림"]
    assert {"④ 같은 불만 점검 승인", "② 메뉴판 바꾸기 승인", "③ 포스터 승인"} <= set(by_time[("10/7(수)", "15:00")])
    assert "① 단골 재주문 인사 승인" in by_time[("10/10(토)", "10:00")]
    assert "④ 리뷰 답글 승인" in by_time[("10/5(월)", "20:00")]  # 맛 불만 빠른 답글 (④ 부정 리뷰)


def test_week_lists_killer_feature_demo_steps():
    """Killer Feature 네 가지마다 그 기능이 보이는 시각과 까닭 (앱 시험 날짜의 'Killer Feature 시연')."""
    features = {f["key"]: f for f in scenario_week.week_stops("s005")["features"]}
    assert [f["mark"] for f in features.values()] == ["①", "②", "③", "④"]
    steps = lambda key: [(st["day"], st["time"], st["label"]) for st in features[key]["steps"]]  # noqa: E731
    assert ("10/10(토)", "10:00", "한 달 단골에게 재주문 인사") in steps("revisit")
    assert ("10/7(수)", "15:00", "메뉴판 새로 맞추기") in steps("menu") and len(steps("menu")) >= 2
    assert steps("poster")[0] == ("10/7(수)", "15:00", "행사 포스터 만들기")
    assert steps("fix") == [("10/5(월)", "20:00", "불만 리뷰에 사과 답글"), ("10/7(수)", "15:00", "같은 불만 점검 목록")]
    assert "남양 가을 축제" in features["poster"]["steps"][0]["reason"]  # 외부 데이터(행사)가 까닭으로 보인다


def test_go_moves_clock_and_keeps_complaint_signal(monkeypatch):
    """옮긴 시각의 결과에 앞 시각에서 찾은 반복 불만이 이어진다 (점검 승인 요청이 그 시각 묶음에 있다)."""
    monkeypatch.setattr(settings, "dev_clock_enabled", True)
    monkeypatch.setattr(settings, "clova_studio_api_key", "")
    try:
        body = scenario_week.go_to("s005", AT(2026, 10, 7, 15, 5))
        assert body["now"].startswith("2026-10-07T15:05")
        plan = store_snapshot_cache.get_snapshot("s005", wait_for_drafts=False, polish=False).require_plan()
        fixes = [i for i in plan.plan_items if i.task_type == "REVIEW_FIX"]
        assert fixes and fixes[0].approval_request_at == AT(2026, 10, 7, 15, 0)
    finally:
        set_clock_shift(dt.timedelta(0))
        store_snapshot_cache.forget("s005")


def test_test_week_api(monkeypatch):
    monkeypatch.setattr(settings, "dev_tools_enabled", True)
    client = TestClient(create_app())
    assert client.get("/api/dev_tools/test_week", params={"store_id": "s005"}).json()["store_name"] == "초옹장"
    assert client.get("/api/dev_tools/test_week", params={"store_id": "s001"}).json()["error"]["code"] == "NO_TEST_WEEK"
    monkeypatch.setattr(settings, "dev_clock_enabled", False)
    res = client.post("/api/dev_tools/test_go", json={"store_id": "s005", "at": "2026-10-07T15:05:00+09:00"})
    assert res.json()["error"]["code"] == "DEV_CLOCK_OFF"


def test_scenario_file_is_regenerated_the_same(tmp_path, monkeypatch):
    """make_s005.py 로 다시 만들면 올라간 파일과 같다 (손으로 고친 값이 없게)."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("make_s005", test_scenario.SCENARIO_DIR / "make_s005.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "OUT", tmp_path / "s005.json")
    module.main()
    assert (tmp_path / "s005.json").read_text(encoding="utf-8") == test_scenario.path_of("s005").read_text(encoding="utf-8")
