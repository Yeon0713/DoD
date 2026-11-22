"""가게 파일이 많아져도(SQLite 한 연결에 붙일 수 있는 DB 는 10개) DB 연결이 깨지지 않는다. 임시 폴더만 쓴다."""

import datetime as dt

import pytest
from sqlalchemy import insert, select

from app.core.naver_place import PlaceInfo
from app.data_pipeline import read_store_db, registered_stores
from db import models, session


@pytest.fixture
def tmp_data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(session, "DATA_DIR", tmp_path)
    monkeypatch.setattr(registered_stores, "DATA_DIR", tmp_path)
    yield tmp_path
    session.dispose_all()


def _store(store_id: str, name: str) -> dict:
    return {
        "store_id": store_id, "name": name, "category": "돈가스", "address": "강원 춘천시", "lat": 37.86, "lng": 127.75,
        "open_time": dt.time(11), "close_time": dt.time(21), "closed_weekdays": [], "slots": ["10:30", "15:00", "20:30"],
    }


def test_many_store_files_do_not_break_connections(tmp_data_dir):
    for number in range(101, 116):
        registered_stores._create_store_file(f"s{number}")
    assert len(list(tmp_data_dir.glob("s*.db"))) == 15
    read_store_db.read_events()  # 공통 테이블
    with session.store_engine("s115").connect() as conn:
        assert conn.execute(select(models.Store)).all() == []


def test_store_engine_reads_only_its_own_store(tmp_data_dir):
    for store_id, name in (("s101", "가"), ("s102", "나")):
        registered_stores._create_store_file(store_id)
        with session.store_engine(store_id).begin() as conn:
            conn.execute(insert(models.Store), [_store(store_id, name)])
    assert [row["name"] for row in read_store_db._store_rows("s101", select(models.Store.__table__))] == ["가"]
    assert [row["name"] for row in read_store_db._store_rows("s102", select(models.Store.__table__))] == ["나"]


def _place(place_id: str) -> PlaceInfo:
    hours = {"open": "11:00", "close": "21:00"}
    return PlaceInfo(place_id, "시험 가게", "돈가스", "강원 춘천시", "강원 춘천시", 37.86, 127.75, {code: hours for code in ("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN")}, None)


def test_failed_store_file_creation_leaves_no_file(tmp_data_dir, monkeypatch):
    """가게 파일을 만들다 실패하면(예: 붙일 수 있는 DB 수를 넘김) 반쯤 만든 파일을 남기지 않는다. 남으면 서버를 다시 켜도 계속 깨진다."""
    def broken(table):
        raise RuntimeError("표 만들기 실패")

    monkeypatch.setattr(registered_stores, "CreateTable", broken)
    with pytest.raises(RuntimeError):
        registered_stores.register(_place("P1"))
    assert list(tmp_data_dir.glob("s*.db")) == []
