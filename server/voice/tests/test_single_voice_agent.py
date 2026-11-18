"""단일 에이전트 A 의 음성 브리핑 준비 (비교용): 답글들과 고칠 점을 에이전트 하나가 한 번에. 가짜 CLOVA."""

import pytest

from Harness.agents import quote_judge, reply_critic, single_agent
from Harness.tests.fakes import FakeClova, call
from voice.agents import improve_tip, voice_reply
from voice.context import load
from voice.tests.test_agents import loaded

NOW_TEXT = "2026-11-17T09:00:00+09:00"
GOOD = "배달이 늦어 식은 음식을 드시게 해서 정말 죄송합니다. 다음 주문은 더 빨리, 따뜻하게 보내 드릴게요."
PRAISE = "곱창전골 국물을 좋게 봐 주셔서 감사해요! 비 오는 날엔 곱창전골이 더 생각나실 거예요."
TIP = "저녁엔 배달 예상 시간을 넉넉히 안내해 보세요"
OCCASION = {"kind": "weather", "label": "비 소식", "explanation": "목요일에 비가 와서 그날 아침에 올려요", "post_at": "2026-11-19T08:00:00+09:00"}


def reply(review_id="rv_0412", text=GOOD, quoted=("배달이 너무 늦어서",), menus=()):
    return {"review_id": review_id, "text": text, "quoted_review_words": list(quoted), "menus_mentioned": list(menus), "facts_used": []}


def submit(replies, tip=None):
    args = {"replies": list(replies)}
    if tip is not None:
        args["tip"] = tip
    return [call("submit_voice_all", args)]


@pytest.fixture
def no_critic(monkeypatch):
    called = []
    monkeypatch.setattr(reply_critic, "inspect", lambda *a, **k: called.append("inspect"))
    monkeypatch.setattr(quote_judge, "ask", lambda *a, **k: called.append("ask"))
    return called


def jobs(view):
    return [{"review": view.review("rv_0412"), "kind": "AUTO", "occasion": None},
            {"review": view.review("rv_0409"), "kind": "SCHEDULED", "occasion": OCCASION}]


def test_replies_and_tip_in_one_run_with_rejection_and_resubmit(clova_on, no_critic):
    loaded()
    fake = clova_on(FakeClova(
        [call("get_reply_occasion", {"review_id": "rv_0409"}), call("get_review_counts", {})],
        submit([reply(), reply("rv_0409", PRAISE, ("곱창전골 국물이 진하고",), ("곱창전골",))],
               {"tip": "배달 시간을 다시 보세요", "evidence": []}),  # 고칠 점 근거가 없다 → 고칠 점만 거절
        submit([reply(), reply("rv_0409", PRAISE, ("곱창전골 국물이 진하고",), ("곱창전골",))],
               {"tip": TIP, "evidence": ["get_review_counts"]}),
    ))
    view = load("s001")
    from voice.clock import parse

    result = single_agent.prepare_voice(view, jobs(view), parse(NOW_TEXT))

    assert result["replies"]["rv_0412"] == {"text": GOOD, "source": "AGENT", "notes": []}
    assert result["replies"]["rv_0409"]["text"] == PRAISE and result["tip"] == {"text": TIP, "source": "AGENT"}
    rejection = fake.tool_messages(2)[-1]
    assert "[고칠 점] evidence 에 근거를 1개 이상" in rejection and "[rv_0412]" not in rejection
    occasion = fake.tool_messages(1)[0]
    assert '"label": "비 소식"' in occasion and '"post_day": "목요일"' in occasion  # review_id 로 고른 답글의 상황
    assert no_critic == [] and fake.done()

    first = fake.requests[0]
    system, user = first["messages"][0]["content"], first["messages"][1]["content"]
    assert "'도나네 곱창 역삼점'의 사장님" in system and "[제출 전에 스스로 확인]" in system  # 팀 답글 프롬프트 + 단일 안내
    assert "review_id: rv_0412" in user and "review_id: rv_0409" in user and "[할 일 3] 고칠 점" in user
    assert user.count("오늘:") == 1
    names = [tool["function"]["name"] for tool in first["tools"]]
    assert names == ["get_menu_list", "get_store_facts", "get_reply_occasion", "get_negative_reviews", "get_review_counts", "submit_voice_all"]


def test_budget_is_sum_and_failure_falls_back_to_templates(clova_on, no_critic):
    loaded()
    view = load("s001")
    from voice.clock import parse

    now = parse(NOW_TEXT)
    task = {"date": "2026-11-17", "replies": [{"kind": "AUTO", "review_id": "rv_0412", "occasion": None}] * 2, "tip": True}
    budget = single_agent.voice_spec(task).budget
    assert budget.max_steps == 2 * voice_reply.SPEC.budget.max_steps + improve_tip.SPEC.budget.max_steps

    clova_on(FakeClova(500))  # CLOVA 실패 → B 와 같은 물러나기(템플릿)
    result = single_agent.prepare_voice(view, jobs(view), now)
    assert result["replies"]["rv_0412"]["source"] == "FALLBACK"
    assert result["replies"]["rv_0412"]["text"].startswith("늦은 배달로 불편을 드려 죄송합니다")
    assert result["tip"]["source"] == "FALLBACK" and result["tip"]["text"]
    assert no_critic == []
