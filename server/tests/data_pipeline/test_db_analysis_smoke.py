"""DB 로더 → 분석 스모크 테스트. 앱과 같은 길(build_analysis_inputs)로 기준선·달력이 오류 없이 나오는지만 본다.

지호의 개발 DB(db/data/*.db)는 읽기만 한다. 값은 DB 내용에 따라 바뀌므로 고정하지 않는다.
손계산 값은 tests/analysis 의 고정 데이터(fixtures/mock_v1)와 점심·저녁·밤 테스트가 확인한다.
"""

import datetime as dt
import hashlib

from app.analysis.pattern.baseline import build_baselines
from app.analysis.pattern.sales_daily import build_sales_daily
from app.analysis.special_cells import cell_keys, find_special_cells
from app.analysis.store_calendar.calendar_day import build_calendar_days
from app.core.seoul_time import SEOUL
from app.data_pipeline import registered_stores
from app.data_pipeline.db_rows_to_analysis_inputs import build_analysis_inputs
from db.session import DATA_DIR

NOW = dt.datetime(2026, 11, 17, 22, 30, tzinfo=SEOUL)
DAYPARTS = ["LUNCH", "DINNER", "NIGHT"]


def db_file_hashes() -> dict[str, str]:
    return {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(DATA_DIR.glob("*.db"))}


def test_db_inputs_give_baselines_and_calendar_without_writing(tmp_path, monkeypatch):
    # 리뷰를 읽을 때 등록 기록(registry.db)을 열면서 표를 만들 수 있어, 실제 파일 대신 임시 파일을 쓰게 한다
    monkeypatch.setattr(registered_stores, "REGISTRY_PATH", tmp_path / "registry.db")
    before = db_file_hashes()

    inputs = build_analysis_inputs("s001", NOW)
    assert [r.daypart for r in inputs.store.dayparts] == DAYPARTS

    rows = build_sales_daily(inputs, NOW).rows
    assert rows and {r.daypart for r in rows} == set(DAYPARTS)
    excluded = cell_keys(find_special_cells(inputs, rows[0].date, NOW.date()))
    baselines = build_baselines(rows, excluded, NOW.date(), DAYPARTS)
    assert len(baselines) == 7 * 3

    calendar = build_calendar_days(inputs, NOW)
    assert len(calendar) == 35 * 3 and calendar[0].date == NOW.date()
    assert {r.daypart for r in calendar} == set(DAYPARTS)

    assert db_file_hashes() == before  # DB 파일은 한 바이트도 바뀌지 않았다
