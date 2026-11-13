"""메뉴판 원래 순서 테스트. server/ 폴더에서 `python -m pytest` 로 실행한다."""

import datetime as dt
import logging

import pytest

from app.core.naver_place import PlaceInfo, PlaceMenu
from app.core.seoul_time import SEOUL
from app.data_pipeline import registered_stores
from app.data_pipeline.db_rows_to_analysis_inputs import build_analysis_inputs
from app.data_pipeline.menu_original_order import original_menu_order, original_order

LOGGER_NAME = "app.data_pipeline.menu_original_order"
NOW = dt.datetime(2026, 11, 12, 15, 0, tzinfo=SEOUL)


def row(menu_id: int, name: str) -> dict:
    """read_store_db.read_menus 한 줄"""
    return {"menu_id": menu_id, "name": name, "category": "main", "price": 10000}


def ids(menus) -> list[str]:
    return [menu.menu_id for menu in menus]


def test_mock_store_keeps_menu_id_order_with_string_ids():
    menus = original_order([row(3, "만두"), row(1, "국수"), row(2, "비빔국수")], None)
    assert ids(menus) == ["1", "2", "3"]  # 분석 입력(AnalysisInputs.menus)과 같은 문자열 id
    assert [menu.name for menu in menus] == ["국수", "비빔국수", "만두"]


def test_registered_store_follows_place_order_and_drops_menus_gone_from_place():
    db = [row(1, "국수"), row(2, "비빔국수"), row(3, "만두"), row(4, "전")]  # 4 전은 플레이스에서 내려감
    assert ids(original_order(db, ["만두", "국수", "비빔국수"])) == ["3", "1", "2"]


def test_same_names_pair_up_in_order():
    db = [row(1, "후라이드"), row(2, "양념"), row(3, "후라이드")]  # 등록 때 화면 순서로 번호를 붙였다
    assert ids(original_order(db, ["후라이드", "양념", "후라이드"])) == ["1", "2", "3"]
    assert ids(original_order(db, ["양념", "후라이드", "후라이드"])) == ["2", "1", "3"]


def test_extra_same_name_in_db_is_treated_as_gone_from_place():
    db = [row(1, "후라이드"), row(2, "양념"), row(3, "후라이드")]
    assert ids(original_order(db, ["후라이드", "양념"])) == ["1", "2"]  # 남는 3 은 화면에서 사라진 메뉴


def test_place_menu_missing_from_db_is_dropped_with_warning(caplog):
    db = [row(1, "후라이드"), row(2, "양념")]
    with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
        menus = original_order(db, ["후라이드", "간장", "양념", "후라이드"], store_id="s101")  # 간장, 두 번째 후라이드는 가게 파일에 없음
    assert ids(menus) == ["1", "2"]
    assert len(caplog.records) == 2
    assert "간장" in caplog.records[0].getMessage()
    assert all("s101" in record.getMessage() for record in caplog.records)  # 어느 가게 일인지 남긴다


def test_names_match_after_trimming_spaces_only():
    db = [row(1, "양념치킨"), row(2, "물냉면")]
    assert ids(original_order(db, ["  양념치킨 ", "물 냉면"])) == ["1"]  # 안쪽 띄어쓰기는 다른 이름


def test_empty_place_menus_fall_back_to_menu_id_order_with_warning(caplog):
    db = [row(2, "양념"), row(1, "후라이드")]
    with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
        assert ids(original_order(db, [], store_id="s101")) == ["1", "2"]  # 등록한 가게인데 메뉴를 못 읽음
    assert len(caplog.records) == 1
    assert "s101" in caplog.records[0].getMessage()


def test_mock_store_logs_no_warning(caplog):
    with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
        original_order([row(1, "후라이드")], None)
    assert caplog.records == []


def test_mock_store_order_uses_the_same_ids_as_analysis_inputs():
    menus = original_menu_order("s001")
    analysis_ids = [menu.menu_id for menu in build_analysis_inputs("s001", NOW).menus]
    assert ids(menus) == sorted(analysis_ids, key=int)
    assert all(isinstance(menu_id, str) for menu_id in ids(menus))


def test_registered_store_still_uses_naver_menu_order(monkeypatch):
    info = PlaceInfo(
        place_id="123456", name="등록 가게", category="음식점", road_address="", address="",
        lat=37.86, lng=127.75, weekly_hours={}, break_time=None,
        menus=[PlaceMenu("만두", 10000, None), PlaceMenu("국수", 10000, None)],
    )
    monkeypatch.setattr(registered_stores, "place_info", lambda store_id: info)
    monkeypatch.setattr("app.data_pipeline.read_store_db.read_menus", lambda store_id: [row(1, "국수"), row(2, "만두"), row(3, "콜라")])
    assert ids(original_menu_order("s101")) == ["2", "1"]


@pytest.mark.parametrize("place_id, store_id", [("1909851296", "s004"), ("2004174048", "s005")])
def test_linked_mock_store_keeps_all_original_menus_after_register_and_refresh(tmp_path, monkeypatch, place_id, store_id):
    monkeypatch.setattr(registered_stores, "REGISTRY_PATH", tmp_path / "registry.db")
    original = original_menu_order(store_id)
    assert len(original) > 2
    info = PlaceInfo(
        place_id=place_id, name="테스트 가게", category="음식점", road_address="", address="",
        lat=37.86, lng=127.75, weekly_hours={}, break_time=None,
        menus=[PlaceMenu(menu.name, menu.price, None) for menu in reversed(original[:2])],
    )

    assert registered_stores.register(info) == store_id
    assert registered_stores.place_info(store_id) is not None  # 목업 매장에도 등록 정보가 생긴다
    assert original_menu_order(store_id) == original  # 화면에 없는 토핑·음료도 원래 순서에 남는다

    info.menus = [PlaceMenu(original[-1].name, original[-1].price, None)]
    registered_stores.refresh(store_id, info)
    assert original_menu_order(store_id) == original
