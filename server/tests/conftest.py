"""모든 테스트에 공통으로 적용하는 설정."""

import pytest

from app.core import clova_usage_log


@pytest.fixture(autouse=True)
def separate_clova_usage_log(tmp_path, monkeypatch):
    """테스트가 가짜 CLOVA 답으로 남기는 기록이 실제 기록 파일(db/app_data/clova_usage.db)에 섞이지 않게 한다."""
    monkeypatch.setattr(clova_usage_log, "LOG_PATH", tmp_path / "clova_usage.db")
