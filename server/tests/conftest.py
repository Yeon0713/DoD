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
def no_agent_cache_file(monkeypatch):
    """에이전트 결과 캐시(Harness/cache.py)는 메모리만 쓴다. 실제 캐시 파일(db/app_data/harness_cache.db)을 읽거나 쓰지 않는다."""
    from Harness import cache

    monkeypatch.setattr(cache, "CACHE_PATH", None)


@pytest.fixture(autouse=True)
def separate_demo_scan_files(tmp_path, monkeypatch):
    """시연 훑기 결과 파일이 실제 폴더(db/app_data/demo_scans)에 쌓이지 않게 한다."""
    monkeypatch.setattr(demo_week_scan, "SAVE_DIR", tmp_path / "demo_scans")


@pytest.fixture(autouse=True)
def separate_registry_db(tmp_path, monkeypatch):
    """등록 기록 DB(db/app_data/registry.db: 등록 가게, 사장님 확인, 예약)를 고치지 않게, 테스트마다 빈 임시 DB 를 쓴다.
    계산할 때 네이버 예약 동기화(목업)가 예약을 써 넣으므로 실제 파일에 쌓이지 않게 한다."""
    from app.data_pipeline import registered_stores, store_logo

    monkeypatch.setattr(registered_stores, "REGISTRY_PATH", tmp_path / "registry_for_test.db")
    monkeypatch.setattr(store_logo, "LOGO_DIR", tmp_path / "logos")  # 로고 파일도 실제 폴더(db/app_data/logos)에 쓰지 않는다


@pytest.fixture(autouse=True)
def separate_test_accounts_db(tmp_path, monkeypatch):
    """테스트 계정 DB(db/test_accounts.db)를 고치지 않게, 테스트마다 기본값으로 새로 만든 임시 DB 를 쓴다."""
    monkeypatch.setattr(test_accounts, "DB_PATH", tmp_path / "test_accounts.db")


@pytest.fixture(autouse=True)
def no_real_kma_calls(monkeypatch):
    """server/.env 에 기상청 키가 있어도 테스트가 실제 기상청을 부르지 않게 한다 (날씨 테스트는 가짜 응답을 쓴다)."""
    from app.core.config import settings
    from app.weather import stations

    monkeypatch.setattr(settings, "kma_api_key", "")
    stations.clear_cache()


@pytest.fixture
def logo_png() -> bytes:
    """흰 바탕 가운데에 갈색 그림이 있는 로고 PNG (가게 로고 바탕 지우기 시험용)"""
    import io

    from PIL import Image, ImageDraw

    image = Image.new("RGB", (400, 300), (255, 255, 255))
    draw = ImageDraw.Draw(image)
    draw.ellipse((150, 100, 250, 200), fill=(72, 52, 44))
    draw.rectangle((190, 60, 210, 100), fill=(72, 52, 44))
    out = io.BytesIO()
    image.save(out, "PNG")
    return out.getvalue()
