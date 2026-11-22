"""G5 ~ G7: 사장님이 정한 보상 문장만 답글에 붙는다 (donna-voice/docs/test-scenarios-closed-loop.md G).

프리셋은 코드가 붙이고 LLM 에 지시로 넘기지 않는다. reply_critic.owner_gives() 는 지시문에 보상 말투가 있으면 답글의
보상 문장을 모두 허락하므로, 프리셋을 지시로 넘기면 LLM 이 지어낸 "환불"도 통과하기 때문이다.
"""

import pytest

from Harness import guards
from Harness.agents import reply_critic
from Harness.tests.fakes import FakeClova, call
from app.core.config import settings
from voice import config, context, repo
from voice.agents import voice_reply
from voice.jobs import cause
from voice.tests.conftest import choongjang, new_agents_off

PRESET = "다음 주문 때 감자전 하나를 서비스로 드릴게요."


def test_g5_made_up_compensation_is_replaced():
    text = "국물이 새서 죄송합니다. 환불해 드릴게요. " + PRESET
    safe, notes = voice_reply.safe_reply(text, PRESET, cause.DETAILS["leak"]["reply"])
    assert safe == cause.DETAILS["leak"]["reply"] + " " + PRESET and notes == ["보상 문장 걸러냄"]
    kept, notes = voice_reply.safe_reply(cause.DETAILS["leak"]["reply"] + " " + PRESET, PRESET, "x")
    assert kept.endswith(PRESET) and notes == []


def test_g5_agent_draft_with_refund_falls_back(monkeypatch):
    """에이전트가 보상을 쓴 초안을 내면 감사팀이 되돌리고(2번), 끝내 불합격해도 원인별 템플릿 + 사장님 문장이 된다."""
    donna = choongjang(permission=None)  # 픽스처 준비(브리핑 답글)는 에이전트를 끈 채로. 묻는 가게 (자동 답글에는 보상 문장이 없다)
    donna.clock("2026-11-17T15:40:00+09:00")
    new_agents_off(monkeypatch)  # 교정 카드·팀장 등 새 사원은 끈다 (답글 에이전트만 본다)
    refund = call("submit_reply", {"text": "국물이 새서 정말 죄송합니다. 다음 주문은 전액 환불해 드릴게요.", "quoted_review_words": ["국물이 다 새서"],
                                   "menus_mentioned": [], "facts_used": []})
    monkeypatch.setattr(settings, "clova_studio_api_key", "test-key")
    monkeypatch.setattr(config, "ALERT_AGENT_REPLY", True)  # 알림 답글을 에이전트로 쓰는 길 (기본은 템플릿)
    found = [call("submit_judgement", {"found": True, "quotes": ["다음 주문은 전액 환불해 드릴게요."]})]
    # 첫 제출 + 되돌림 2번 (감사 불합격은 1차 거절과 따로 센다). 같은 글의 보상 판정은 캐시라 처음 한 번만 묻는다
    fake = FakeClova([refund], found, [refund], [refund])
    monkeypatch.setattr(context, "post", fake)
    rid = donna.demo_review("leak")
    text = donna.open_notice()["cards"][0]["reply"]["text"]
    assert "환불" not in text and text.endswith(PRESET)
    assert repo.get("alert", f"al_{rid}")["reply_source"] == "TEMPLATE"  # 인턴 가게: 끝내 불합격 → 템플릿 (감사팀 결정 7)
    assert fake.done()


def test_g6_preset_is_never_an_instruction(monkeypatch):
    seen = []
    original = reply_critic.inspect

    def spy(reply, ctx, **kwargs):
        seen.append(kwargs.get("owner_instruction"))
        return original(reply, ctx, **kwargs)

    monkeypatch.setattr(reply_critic, "inspect", spy)
    donna = choongjang()
    donna.clock("2026-11-17T15:40:00+09:00")
    donna.demo_review("leak")
    donna.open_notice()
    donna.turn("응, 진행해")
    assert all(instruction is None for instruction in seen)
    # 원인별 템플릿에는 보상 말이 없다 (프리셋을 빼고 보면 깨끗해야 safe_reply 가 걸러내지 않는다)
    for spec in [*cause.DETAILS.values()]:
        assert not guards.promise_hit(spec["reply"]) and not guards.PRICE_RE.search(spec["reply"]), spec["reply"]
    for text in cause.PLAIN.values():
        assert not guards.promise_hit(text), text


@pytest.mark.parametrize("value, ok", [
    ("[메뉴]를 서비스로 드려요", False), ("가" * 61, False), ("짧아", False), ("음료 드려요. 쿠폰도 드려요.", False),
    ("다음 주문 때 음료 하나를 서비스로 드릴게요.", True)])
def test_g7_preset_checked(value, ok):
    donna = choongjang(at=None)
    response = donna.client.patch("/v1/settings", json={"store_id": "s005", "compensation": {"taste_temp": value}})
    if ok:
        assert response.status_code == 200 and response.json()["compensation"]["taste_temp"] == value
    else:
        assert response.status_code == 400 and response.json()["error"]["code"] == "bad_compensation"


def test_g7_unknown_kind_and_clear():
    donna = choongjang(at=None)
    bad = donna.client.patch("/v1/settings", json={"store_id": "s005", "compensation": {"refund": "다 돌려드려요"}})
    assert bad.status_code == 400
    cleared = donna.client.patch("/v1/settings", json={"store_id": "s005", "compensation": {"packaging": None}}).json()
    assert cleared["compensation"] == {"packaging": None, "missing": "빠진 메뉴는 다음 주문 때 함께 챙겨 드릴게요.",
                                       "taste_temp": None, "hall_service": None}
