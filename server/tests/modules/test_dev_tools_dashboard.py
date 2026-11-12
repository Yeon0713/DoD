"""개발자 대시보드 API(/api/dev_tools)와 CLOVA 사용 기록 테스트. 진짜 CLOVA 는 부르지 않는다."""

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core import clova, clova_usage_log
from app.core.config import settings
from app.main import create_app


def fake_post(answer: str, prompt_tokens: int = 500, completion_tokens: int = 20, status: int = 200):
    def post(*args, **kwargs):
        body = {"result": {"message": {"content": answer}, "usage": {"promptTokens": prompt_tokens, "completionTokens": completion_tokens, "totalTokens": prompt_tokens + completion_tokens}}}
        return httpx.Response(status, json=body)

    return post


def test_dashboard_is_closed_by_default(monkeypatch):
    monkeypatch.setattr(settings, "dev_tools_enabled", False)
    client = TestClient(create_app())
    assert client.get("/api/dev_tools/overview").status_code == 404
    assert client.get("/dev-dashboard/").status_code == 404


def test_clova_call_is_logged_with_tokens_and_verdict(monkeypatch):
    monkeypatch.setattr(settings, "clova_studio_api_key", "test-key")
    monkeypatch.setattr(settings, "clova_price_input_per_1k", 1.0)
    monkeypatch.setattr(settings, "clova_price_output_per_1k", 4.0)
    assert clova.ask("시스템", "리뷰 글", post=fake_post("답글"), feature="reply_draft", store_id="s001") == "답글"
    clova_usage_log.set_verdict(False, "보상 약속")
    clova.ask("시스템", "글", post=fake_post("", status=500), feature="polish:notice", store_id="s001")

    usage = clova_usage_log.usage_summary(1)
    assert usage["total"]["calls"] == 2 and usage["total"]["failed"] == 1
    assert usage["total"]["input_tokens"] == 500 and usage["total"]["output_tokens"] == 20
    assert usage["total"]["cost_won"] == pytest.approx(0.58)  # 500×1/1000 + 20×4/1000
    quality = clova_usage_log.quality_summary(10)
    assert quality["reject_reasons"] == [{"reason": "보상 약속", "count": 1}]


@pytest.fixture
def dashboard(monkeypatch):
    monkeypatch.setattr(settings, "dev_tools_enabled", True)
    monkeypatch.setattr(settings, "clova_studio_api_key", "")  # 가게 계산 때 CLOVA 를 부르지 않게
    monkeypatch.setattr(settings, "sentence_polish_enabled", False)
    return TestClient(create_app())


@pytest.mark.parametrize(
    "path",
    ["/api/dev_tools/overview", "/api/dev_tools/stores", "/api/dev_tools/ai_usage", "/api/dev_tools/ai_quality", "/api/dev_tools/system"],
)
def test_dashboard_apis_open_when_enabled(dashboard, path):
    assert dashboard.get(path).status_code == 200


def test_dashboard_page_is_served(dashboard):
    page = dashboard.get("/dev-dashboard/")
    assert page.status_code == 200 and "개발자 대시보드" in page.text


def test_system_tab_does_not_send_key_values(dashboard, monkeypatch):
    monkeypatch.setattr(settings, "naver_api_hub_client_secret", "secret-value-should-not-leak")
    body = dashboard.get("/api/dev_tools/system").text
    assert "secret-value-should-not-leak" not in body
