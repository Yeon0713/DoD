"""모든 테스트에 공통으로 적용하는 설정."""

import pytest

from app.core import clova_usage_log


@pytest.fixture(autouse=True)
def separate_clova_usage_log(tmp_path, monkeypatch):
    """테스트가 가짜 CLOVA 답으로 남기는 기록이 실제 기록 파일(db/app_data/clova_usage.db)에 섞이지 않게 한다."""
    monkeypatch.setattr(clova_usage_log, "LOG_PATH", tmp_path / "clova_usage.db")


@pytest.fixture(autouse=True)
def no_real_kma_calls(monkeypatch):
    """server/.env 에 기상청 키가 있어도 테스트가 실제 기상청을 부르지 않게 한다 (날씨 테스트는 가짜 응답을 쓴다)."""
    from app.core.config import settings
    from app.weather import stations

    monkeypatch.setattr(settings, "kma_api_key", "")
    stations.clear_cache()
