"""모든 테스트에 공통으로 적용하는 설정."""

import pytest

from app.core import clova_usage_log
from app.modules.auth import test_accounts
from app.modules.dev_tools import demo_week_scan


@pytest.fixture(autouse=True)
def separate_clova_usage_log(tmp_path, monkeypatch):
    """테스트가 가짜 CLOVA 답으로 남기는 기록이 실제 기록 파일(db/app_data/clova_usage.db)에 섞이지 않게 한다."""
    monkeypatch.setattr(clova_usage_log, "LOG_PATH", tmp_path / "clova_usage.db")


@pytest.fixture(autouse=True)
def separate_demo_scan_files(tmp_path, monkeypatch):
    """시연 훑기 결과 파일이 실제 폴더(db/app_data/demo_scans)에 쌓이지 않게 한다."""
    monkeypatch.setattr(demo_week_scan, "SAVE_DIR", tmp_path / "demo_scans")


@pytest.fixture(autouse=True)
def separate_test_accounts_db(tmp_path, monkeypatch):
    """테스트 계정 DB(db/test_accounts.db)를 고치지 않게, 테스트마다 기본값으로 새로 만든 임시 DB 를 쓴다."""
    monkeypatch.setattr(test_accounts, "DB_PATH", tmp_path / "test_accounts.db")
