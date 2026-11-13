"""스냅샷에 메뉴판 배치안(menu_boards)이 붙는지 확인한다. server/ 폴더에서 `python -m pytest` 로 실행한다.

CLOVA 키를 비워서 돌린다. 뒤에서 부르기를 보는 테스트만 가짜 키와 가짜 후보 함수를 쓴다(밖으로 요청을 보내지 않는다).
"""

import datetime as dt
import json
import logging
import threading
import time

import pytest

from app.core.config import settings
from app.core.seoul_time import SEOUL
from app.data_pipeline import read_store_db, registered_stores, store_snapshot_cache
from app.menu_board import for_snapshot
from app.menu_board import menu_candidates as candidates_module

NOW = dt.datetime(2026, 11, 17, 13, 50, tzinfo=SEOUL)  # 11/18(겨울 시작) 메뉴판 카드의 승인 요청 직전


@pytest.fixture(autouse=True)
def no_clova(monkeypatch):
    monkeypatch.setattr(settings, "sentence_polish_enabled", False)
    monkeypatch.setattr(settings, "clova_studio_api_key", "")
    store_snapshot_cache.clear_all()
    candidates_module.forget_all()
    yield
    candidates_module.wait_for_background()
    candidates_module.forget_all()
    store_snapshot_cache.clear_all()


def menu_order_ids(snapshot) -> set[str]:
    return {item.plan_id for item in snapshot.plan.plan_items if item.task_type == "MENU_ORDER"}


def test_snapshot_has_a_menu_board_for_every_menu_order_card():
    snapshot = store_snapshot_cache.get_snapshot("s001", NOW)
    assert set(snapshot.menu_boards) == menu_order_ids(snapshot)
    board = snapshot.menu_boards["MENU_ORDER:2026-11-18:2026-11-18"]
    assert board.basis == "season_winter"
    assert board.reason  # LLM 이 없어도 이유 문구가 있다


def test_missing_kma_weather_keeps_menu_boards_and_all_menus(tmp_path, monkeypatch):
    monkeypatch.setattr(registered_stores, "REGISTRY_PATH", tmp_path / "registry.db")
    weather = [
        {"date": NOW.date() + dt.timedelta(days=offset), "temp_max": None, "temp_min": None, "precip_mm": None}
        for offset in range(-30, 5)
    ]
    monkeypatch.setattr(read_store_db, "read_weather", lambda store_id: weather)
    snapshot = store_snapshot_cache.get_snapshot("s001", NOW)

    assert snapshot.inputs.weather and all(w.temp_max is None for w in snapshot.inputs.weather)
    assert snapshot.menu_boards and set(snapshot.menu_boards) == menu_order_ids(snapshot)
    bases = {board.basis for board in snapshot.menu_boards.values()}
    assert bases & {event.event_id for event in snapshot.inputs.events}
    assert all(board.basis != "season_winter" for board in snapshot.menu_boards.values())
    menu_ids = {menu.menu_id for menu in snapshot.inputs.menus}
    assert all({menu.menu_id for menu in board.arrangement.order} == menu_ids for board in snapshot.menu_boards.values())


def test_assembly_error_leaves_the_rest_of_the_snapshot_unchanged(monkeypatch, caplog):
    normal = store_snapshot_cache.get_snapshot("s001", NOW)
    store_snapshot_cache.clear_all()

    def broken(*args, **kwargs):
        raise RuntimeError("조립 버그")

    monkeypatch.setattr(for_snapshot, "assemble_menu_board_cards", broken)
    with caplog.at_level(logging.INFO):
        failed = store_snapshot_cache.get_snapshot("s001", NOW)
    assert failed.menu_boards == {}
    for name in ("sales_daily", "calendar_cells", "customer_cycles", "reviews", "risk_signals", "settings", "plan", "draft_texts"):
        assert getattr(failed, name) == getattr(normal, name), name
    records = [r for r in caplog.records if r.name == for_snapshot.__name__]
    assert len(records) == 1 and records[0].exc_info is not None
    assert "s001" in records[0].getMessage() and "실패" in records[0].getMessage()


def test_store_without_a_plan_logs_differently_from_a_failure(caplog):
    with caplog.at_level(logging.INFO):
        snapshot = store_snapshot_cache.get_snapshot("s002", NOW)  # 자정 넘김 매장: 계획 엔진이 계획을 만들지 않는다
    assert snapshot.menu_boards == {}
    records = [r for r in caplog.records if r.name == for_snapshot.__name__]
    assert len(records) == 1 and records[0].exc_info is None
    assert "s002" in records[0].getMessage() and "계획 엔진 결과가 없어" in records[0].getMessage()


def test_plan_without_menu_order_cards_logs_no_cards(monkeypatch, caplog):
    plan = store_snapshot_cache.get_snapshot("s001", NOW).plan
    no_cards = plan.model_copy(update={"plan_items": [item for item in plan.plan_items if item.task_type != "MENU_ORDER"]})
    with caplog.at_level(logging.INFO):
        assert for_snapshot.snapshot_menu_boards("s001", {"name": "", "category": ""}, None, None, no_cards, []) == {}
    assert "s001" in caplog.text and "카드가 없어" in caplog.text


def test_snapshot_does_not_wait_for_clova(monkeypatch):
    monkeypatch.setattr(settings, "clova_studio_api_key", "test-key")
    monkeypatch.setattr(store_snapshot_cache, "write_drafts", lambda *args, **kwargs: {})  # 답글 초안도 밖으로 보내지 않는다
    gate = threading.Event()
    asked = []

    def slow_clova(system, user, **kwargs):  # CLOVA 대신: 30초까지 막혔다가 마지막 메뉴를 고른다
        asked.append(user.split("\n", 1)[0])
        gate.wait(timeout=30)
        last_id = json.loads(user.split("\n")[2])[-1]["id"]
        return json.dumps({"menu_ids": [last_id], "reason": "잘 어울려요"}, ensure_ascii=False)

    monkeypatch.setattr(candidates_module.clova, "ask", slow_clova)
    try:
        started = time.monotonic()
        first = store_snapshot_cache.get_snapshot("s001", NOW)
        assert time.monotonic() - started < 20  # CLOVA(여기서는 30초 막힘)를 기다리지 않았다
        board = first.menu_boards["MENU_ORDER:2026-11-18:2026-11-18"]
        assert board.reason != "잘 어울려요."  # 아직 후보가 없어 데이터 점수만으로 만든 배치안
    finally:
        gate.set()  # 테스트가 실패해도 막아 둔 가짜 CLOVA 를 풀어 다른 테스트에 남지 않게 한다
        candidates_module.wait_for_background(timeout=35)
    assert asked.count("상황: 겨울(추운 날씨)") == 1  # 같은 키는 진행 중이면 다시 맡기지 않는다

    store_snapshot_cache.clear_all()  # 다음 계산 때 반영된다
    second = store_snapshot_cache.get_snapshot("s001", NOW)
    assert second.menu_boards["MENU_ORDER:2026-11-18:2026-11-18"].reason == "잘 어울려요."
