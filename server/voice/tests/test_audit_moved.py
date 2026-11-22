"""감사팀 4단계: 옮긴 LLM 검사(reply_critic, staff_scope)가 2차 감사로 돌고, 불합격이면 같은 대화로 지적을 돌려준다."""

from Harness.tests.fakes import FakeClova, call
from voice import config, repo
from voice.agents import fix_card, voice_reply
from voice.context import load
from voice.tests.test_agents import FIX, GOOD, critic_pass, judged, loaded, submit
from voice.tests.test_fix_card import CARD_OK
from voice.tests.test_fix_card import GOOD as CARD
from voice.tests.test_fix_card import agent  # noqa: F401 (fixture)

BLAME = "배달 기사님이 늦게 오셔서 그랬어요. 죄송합니다. 다음 주문은 더 빨리, 따뜻하게 보내 드릴게요."


def audit_rows(store_id):
    return repo.all_of("audit", store_id)


def test_reply_critic_fail_returns_in_same_conversation_then_passes(clova_on):
    loaded()
    excuse = "배달 기사님이 늦게 오셔서 그랬어요."
    fake = clova_on(FakeClova(
        submit(BLAME), judged(), judged(FIX), judged(), judged(excuse),
        submit(), *critic_pass(),
    ))
    view = load("s001")
    written = voice_reply.write(view, view.review("rv_0412"), "AUTO")
    assert written["text"] == GOOD and written["audit"]["passed"] is True and written["audit"]["rounds"] == 1
    returned = fake.tool_messages(5)[-1]
    assert returned.startswith("감사팀 지적: 검토에서 걸렸어요: 변명·남 탓")
    rows = audit_rows("s001")
    assert [(r["job"], r["status"], r["criterion"], r["final"]) for r in rows] == [
        ("negative_reply", "fail", "BLAME", False), ("negative_reply", "pass", None, True)]
    assert rows[0]["calls"] == 4 and rows[0]["ref"] == "rv_0412" and fake.done()


def test_reply_unchecked_adds_note(clova_on):
    loaded()
    clova_on(FakeClova(submit(), judged(), judged(FIX), judged(), judged(),
                              judged(), 500, 500, 500))  # 마지막 질문(리뷰와 상관없는 말)을 부르지 못함
    view = load("s001")
    written = voice_reply.write(view, view.review("rv_0412"), "AUTO")
    assert written["text"] == GOOD and written["audit"]["passed"] is None and written["notes"] == ["검토 안 됨"]


def test_staff_scope_fail_returns_then_passes(agent):  # noqa: F811
    buy = {**CARD, "title": "새 포장 용기 사기", "detail": "국물이 안 새는 새 용기를 사서 써 주세요"}
    fake = agent([call("submit_fix_card", buy)], judged("새 용기를 사서"), [call("submit_fix_card", CARD)], *CARD_OK)
    view = load("s005")
    found = fix_card.card_for(view, view.review("rv_0412"))
    assert found["card"]["title"] == CARD["title"] and fake.tool_messages(2)[0].startswith("감사팀 지적: ")
    assert [(r["job"], r["status"]) for r in audit_rows("s005")] == [("review_fix_task", "fail"), ("review_fix_task", "pass")]


def test_card_final_fail_falls_back_to_template(agent):  # noqa: F811
    buy = {**CARD, "title": "새 포장 용기 사기", "detail": "국물이 안 새는 새 용기를 사서 써 주세요"}
    fake = agent([call("submit_fix_card", buy)], judged("새 용기를 사서"), [call("submit_fix_card", buy)], [call("submit_fix_card", buy)])
    view = load("s005")
    found = fix_card.card_for(view, view.review("rv_0412"))
    assert found["card_source"] == "TEMPLATE" and fake.done()  # 같은 글의 판정은 캐시라 한 번만 묻는다


def test_cached_result_is_not_logged_twice(agent, monkeypatch):  # noqa: F811
    agent([call("submit_fix_card", CARD)], *CARD_OK)
    view = load("s005")
    fix_card.card_for(view, view.review("rv_0412"))
    monkeypatch.setattr(config, "agent_on", lambda name: name == "fixcard")
    fix_card.card_for(view, view.review("rv_0412"))  # 캐시에서 되살림 (CLOVA 차례가 없어도 된다)
    assert len(audit_rows("s005")) == 1
