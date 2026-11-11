"""CLOVA X 문장 다듬기 검사 테스트. 진짜 CLOVA 를 부르지 않고 가짜 응답을 넣는다."""

import httpx

from app.core.config import settings
from app.sentence_polish import polish_with_clova
from app.sentence_polish.polish_with_clova import clean_answer, keeps_facts, polish_now

STORE = {"store_id": "s_test", "name": "테스트국수", "category": "국수"}  # 테스트용 가짜 가게


def fake_post(answer: str, status: int = 200):
    def post(*args, **kwargs):
        return httpx.Response(status, json={"result": {"message": {"content": answer}}})

    return post


def test_clean_answer_removes_prefix_and_quotes():
    assert clean_answer('바꾼: "추워져서 5% 늘 것 같아요"\n설명...') == "추워져서 5% 늘 것 같아요"


def test_keeps_facts_requires_same_numbers():
    original = "겨울 영향으로 평소보다 5% 많을 것 같아요"
    assert keeps_facts("calendar_reason", original, "날이 추워져서 5% 정도 늘 것 같아요")
    assert not keeps_facts("calendar_reason", original, "날이 추워져서 조금 늘 것 같아요")


def test_keeps_facts_requires_same_names():
    original = "춘천 겨울 빛 축제 영향으로 평소보다 55% 많을 것 같아요"
    keep = ["춘천 겨울 빛 축제", "토요일"]
    assert keeps_facts("calendar_reason", original, "춘천 겨울 빛 축제로 55%쯤 몰릴 것 같아요", keep)
    assert not keeps_facts("calendar_reason", original, "빛 축제로 55%쯤 몰릴 것 같아요", keep)


def test_keeps_facts_rejects_too_long():
    assert not keeps_facts("calendar_reason", "평소와 비슷할 것 같아요", "가" * 200)


def test_polish_now_uses_answer_or_falls_back(monkeypatch):
    monkeypatch.setattr(settings, "clova_studio_api_key", "test-key")
    original = "겨울 영향으로 평소보다 5% 많을 것 같아요"
    assert polish_now("calendar_reason", original, STORE, post=fake_post("추워져서 5% 정도 늘 것 같아요")) == "추워져서 5% 정도 늘 것 같아요"
    assert polish_now("calendar_reason", original, STORE, post=fake_post("조금 늘 것 같아요")) is None
    assert polish_now("calendar_reason", original, STORE, post=fake_post("", status=500)) is None


def test_polished_returns_original_when_not_done(monkeypatch):
    monkeypatch.setattr(settings, "clova_studio_api_key", "")
    polish_with_clova.forget_all()
    polish_with_clova.request_polish("plan_card", ["포스터를 올려요."], STORE)  # 키가 없으면 아무것도 맡기지 않는다
    assert polish_with_clova.polished("plan_card", "포스터를 올려요.", STORE) == "포스터를 올려요."


def test_prompt_files_fill_store_name():
    prompt = polish_with_clova.load_prompt("calendar_reason", STORE)
    assert "테스트국수" in prompt and "{가게이름}" not in prompt
