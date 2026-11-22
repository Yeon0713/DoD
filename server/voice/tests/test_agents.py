"""에이전트 3종이 Harness runner 로 도는지 (가짜 CLOVA). 도구 호출 → 거절 → 재제출 통과, 실패 → 템플릿."""

from Harness.tests.fakes import FakeClova, call
from voice.agents import improve_tip, intent_judge, voice_reply
from voice.context import load
from voice.tests.conftest import Donna, baseline, new_agents_off
from voice.tests.test_scenario_b import NIGHT_REVIEW

GOOD = "배달이 늦어 식은 음식을 드시게 해서 정말 죄송합니다. 다음 주문은 더 빨리, 따뜻하게 보내 드릴게요."
FIX = "다음 주문은 더 빨리, 따뜻하게 보내 드릴게요."


def judged(*quotes):
    return [call("submit_judgement", {"found": bool(quotes), "quotes": list(quotes)})]


def submit(text=GOOD, quoted=("배달이 너무 늦어서",), menus=()):
    return [call("submit_reply", {"text": text, "quoted_review_words": list(quoted), "menus_mentioned": list(menus), "facts_used": []})]


def loaded() -> Donna:
    donna = Donna()
    donna.clock("2026-11-17T09:00:00+09:00")
    donna.fixtures()
    return donna


def critic_pass(negative=True):
    """검토 질문들의 답: 보상 → (고칠 점) → 가게 사정 → 변명 → 아는 척 → 리뷰와 상관없는 말."""
    return [judged(), *([judged(FIX)] if negative else []), judged(), judged(), judged(), judged()]


def test_voice_reply_tool_rejection_and_resubmit(clova_on):
    loaded()
    fake = clova_on(FakeClova(
        [call("get_menu_list", {}), call("get_store_facts", {})],
        submit(quoted=("배달이 늦었어요",)),  # 리뷰에 없는 말을 옮겼다 → 코드가 거절
        submit(), *critic_pass(),
    ))
    view = load("s001")
    written = voice_reply.write(view, view.review("rv_0412"), "AUTO")
    assert {k: written[k] for k in ("text", "source", "notes")} == {"text": GOOD, "source": "AGENT", "notes": []}
    assert written["audit"]["passed"] is True and written["audit"]["rounds"] == 0  # 2차 감사(감사팀) 한 번에 합격
    assert "'배달이 늦었어요' 는 리뷰에 글자 그대로 없어요" in fake.tool_messages(2)[-1]
    menus = fake.tool_messages(1)[0]
    assert "곱창전골" in menus
    system = fake.requests[0]["messages"][0]["content"]
    assert "'도나네 곱창 역삼점'의 사장님" in system and "[도구 사용]" in system  # 팀 답글 프롬프트 + 음성 백엔드 도구 안내
    assert fake.done()


def test_voice_reply_critic_rejects_compensation(clova_on):
    loaded()
    bad = "늦어서 정말 죄송합니다. 다음 주문 때 음료 서비스로 드릴게요."
    fake = clova_on(FakeClova(submit(bad), judged("다음 주문 때 음료 서비스로 드릴게요."), submit(), *critic_pass()))
    view = load("s001")
    written = voice_reply.write(view, view.review("rv_0412"), "AUTO")
    assert written["text"] == GOOD
    assert "보상 약속" in fake.tool_messages(2)[0]


def test_voice_reply_falls_back_to_template_when_clova_fails(clova_on):
    loaded()
    clova_on(FakeClova(500))
    view = load("s001")
    written = voice_reply.write(view, view.review("rv_0412"), "AUTO")
    assert written["source"] == "FALLBACK" and written["text"].startswith("늦은 배달로 불편을 드려 죄송합니다")


def test_scheduled_reply_sees_the_occasion(clova_on):
    loaded()
    text = "곱창전골 국물을 좋게 봐 주셔서 감사해요! 비 오는 날엔 곱창전골이 더 생각나실 거예요."
    fake = clova_on(FakeClova(
        [call("get_reply_occasion", {})],
        submit(text, quoted=("곱창전골 국물이 진하고",), menus=("곱창전골",)), *critic_pass(negative=False),
    ))
    view = load("s001")
    occasion = {"kind": "weather", "label": "비 소식", "explanation": "목요일에 비가 와서 그날 아침에 올려요", "post_at": "2026-11-19T08:00:00+09:00"}
    written = voice_reply.write(view, view.review("rv_0409"), "SCHEDULED", occasion)
    assert written["source"] == "AGENT" and written["text"] == text
    assert '"label": "비 소식"' in fake.tool_messages(1)[0] and '"post_day": "목요일"' in fake.tool_messages(1)[0]


def test_improve_tip_rejects_ungrounded_numbers(clova_on):
    loaded()
    good = "저녁엔 배달 예상 시간을 넉넉히 안내해 보세요"
    fake = clova_on(FakeClova(
        [call("get_negative_reviews", {}), call("get_review_counts", {})],
        [call("submit_tip", {"tip": "저녁엔 배달 시간을 15분 넉넉히 안내해 보세요", "evidence": ["get_review_counts 저녁 2건"]})],
        [call("submit_tip", {"tip": good, "evidence": ["get_review_counts 저녁 2건"]})],
    ))
    view = load("s001")
    assert improve_tip.suggest(view, view.now) == {"text": good, "source": "AGENT"}
    counts = fake.tool_messages(1)[1]
    assert '"daypart": "저녁", "count": 2' in counts
    assert "도구 결과에 없는 숫자를 썼어요: 15" in fake.tool_messages(2)[-1]


def test_intent_judge_used_only_when_rules_cannot_decide(clova_on, monkeypatch):
    monkeypatch.setenv("VOICE_AGENT_REPLY", "false")  # 에이전트별 스위치: 답글·고칠 점은 템플릿으로, 뜻 판정만 LLM
    monkeypatch.setenv("VOICE_AGENT_IMPROVE", "false")
    new_agents_off(monkeypatch)  # 2026-11-20 에 더한 사원·팀장도 끈다
    donna = loaded()
    donna.run("prepare_briefing")
    fake = clova_on(FakeClova(
        [call("submit_intent", {"intent": "unknown", "owner_said": "그거 뭐였지 그 저기"})],
        [call("submit_intent", {"intent": "not_for_donna", "owner_said": "오늘 국이 좀 짜네"})],
        500,
    ))
    assert donna.turn("오늘 일정 브리핑해 줘")["briefing"]["step"] == 1  # 규칙으로 가르는 말은 LLM 을 부르지 않는다
    assert len(fake.requests) == 0
    assert donna.turn("그거 뭐였지 그 저기")["type"] == "not_understood"
    first = fake.requests[0]
    assert first["toolChoice"] == {"type": "function", "function": {"name": "submit_intent"}}  # 1단계라 처음부터 제출 강제
    assert "도나가 브리핑 중이에요" in first["messages"][1]["content"]
    assert donna.turn("오늘 국이 좀 짜네")["type"] == "ignore"
    # LLM 이 실패하면 heuristic: 도나에게 묻는 말 같으면 못 알아들음
    assert donna.turn("저기 그거 뭐더라")["type"] == "not_understood"
    assert fake.done()


def test_intent_judge_rejects_unknown_intent(clova_on):
    loaded()
    clova_on(FakeClova([call("submit_intent", {"intent": "order.food", "owner_said": "x"})]))
    assert intent_judge.judge(load("s001"), "x", "도나는 듣고만 있어요") is None


def test_scenario_b_with_agent_reply(clova_on):
    payload = baseline()
    payload["reviews"] = [r for r in payload["reviews"] if r["id"] != "rv_0412"]
    payload["hr"] = {**payload["hr"], "negative_reply": "assistant"}  # 묻지 않고 답한다 (인사과 4-a)
    donna = Donna()
    donna.clock("2026-11-16T22:40:00+09:00")
    donna.fixtures(payload)
    clova_on(FakeClova(submit(), *critic_pass()))
    review_id = donna.review(**NIGHT_REVIEW)["review_id"]
    donna.clock("2026-11-16T22:55:00+09:00")  # 22:50 바로 답하기만 돈다 (문 닫은 뒤 리뷰) (브리핑 준비는 다음 날 09:00)
    review = next(r for r in donna.state()["review"] if r["id"] == review_id)
    assert review["reply_status"] == "posted" and review["reply_text"] == GOOD and review["reply_source"] == "AGENT"
    assert review["replied_in_minutes"] == 10
