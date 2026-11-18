"""하네스 테스트 공통 설정. 실제 기록 파일, 실제 CLOVA, 실제 등록 DB 를 건드리지 않는다."""

import pytest

from app.core import clova, clova_usage_log
from app.core.config import settings
from app.data_pipeline import registered_stores
from app.menu_board import menu_candidates
from app.review_reply_writer import write_reply_with_clova
from Harness import cache, limiter, runner, trace
from Harness.spec import RunContext
from Harness.tests.fakes import NOW, make_snapshot


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(clova_usage_log, "LOG_PATH", tmp_path / "clova_usage.db")
    monkeypatch.setattr(trace, "TRACE_PATH", tmp_path / "harness_trace.db")
    monkeypatch.setattr(cache, "CACHE_PATH", None)  # 에이전트 결과 캐시는 메모리만 (진짜 캐시 파일을 읽거나 쓰지 않는다)
    monkeypatch.setattr(registered_stores, "REGISTRY_PATH", tmp_path / "registry.db")
    monkeypatch.setattr(settings, "clova_studio_api_key", "test-key")
    monkeypatch.setattr(limiter, "sleep", lambda seconds: None)
    # 물러나기(기존 단일 호출)가 진짜 CLOVA 를 부르지 않게. 물러나기 자체를 시험할 때는 테스트에서 다시 바꾼다
    monkeypatch.setattr(clova, "ask", lambda *args, **kwargs: None)
    cache.clear()
    write_reply_with_clova.forget_all()
    menu_candidates.forget_all()
    yield
    cache.clear()


@pytest.fixture
def snapshot():
    return make_snapshot()


@pytest.fixture
def make_ctx(snapshot):
    def make(fake, **extra) -> RunContext:
        return RunContext(snapshot=snapshot, now=NOW, post=fake, **extra)

    return make


@pytest.fixture
def frozen_clock(monkeypatch):
    monkeypatch.setattr(runner, "clock", lambda: 0.0)
