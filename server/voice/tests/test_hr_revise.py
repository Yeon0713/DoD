"""자유로운 수정 ("좀 더 부드럽게", 인사과 9장 6단계). 고친 글은 다시 묻고, 인사과에는 '조금 수정'(edited)으로 남는다."""

from Harness.tests.fakes import FakeClova, call
from voice import config, repo
from voice.dialog import intent_rules
from voice.tests.conftest import FakeGraph, choongjang, hr_log
from voice.tests.test_instagram import Choongjang, chj, connect, to_instagram_step  # noqa: F401 (chj 는 fixture)

SOFT = "국물이 새서 많이 불편하셨을 텐데 정말 죄송해요. 오늘부터 국물 메뉴는 랩을 두 번 씌워 보낼게요."
FIX = "오늘부터 국물 메뉴는 랩을 두 번 씌워 보낼게요."


def judged(*quotes):
    return [call("submit_judgement", {"found": bool(quotes), "quotes": list(quotes)})]


def reply_turns(text: str = SOFT, quoted: tuple = ("국물이 다 새서",)) -> list:
    """답글 에이전트 한 번: 제출 → 검토(보상 없음 → 고칠 점 있음 → 사정·변명·아는 척·상관없는 말 없음)."""
    submit = [call("submit_reply", {"text": text, "quoted_review_words": list(quoted), "menus_mentioned": [], "facts_used": []})]
    return [submit, judged(), judged(FIX), judged(), judged(), judged(), judged()]


def leak_alert():
    donna = choongjang()
    donna.clock("2026-11-17T15:40:00+09:00")
    rid = donna.demo_review("leak")
    donna.open_notice()
    return donna, rid


def test_revise_words():
    for text in ("좀 더 부드럽게 써 줘", "더 짧게", "이모티콘은 쓰지 마"):
        assert intent_rules.match(text, "ask_action").name == "action.revise", text
    assert intent_rules.match("카드는 넣지 마", "ask_action").name == "action.edit"  # 정해진 고침이 먼저
    assert intent_rules.match("이모 여기 물 좀", "answer").name == "not_for_donna"  # 이모(직원 부르는 말)는 그대로


def test_alert_reply_is_revised_then_posted_and_counted_as_edited(monkeypatch):
    from app.core.config import settings
    from voice import context

    donna, rid = leak_alert()  # 픽스처 준비는 에이전트를 끈 채로
    monkeypatch.setattr(config, "agent_on", lambda name: name == "reply")
    monkeypatch.setattr(settings, "clova_studio_api_key", "test-key")
    fake = FakeClova(*reply_turns())
    monkeypatch.setattr(context, "post", fake)
    revised = donna.turn("좀 더 부드럽게 써 줘")
    assert revised["intent"] == "action.revise" and revised["type"] == "ask_action" and revised["say"][0]["text"] == "이렇게 고쳤어요."
    assert revised["cards"][0]["reply"]["text"].startswith(SOFT) and fake.done()
    assert "좀 더 부드럽게" in fake.requests[0]["messages"][-1]["content"]  # 지시와 지난 답글을 에이전트에게 준다
    donna.turn("응, 진행해")
    assert repo.review(rid)["reply_text"].startswith(SOFT)
    assert hr_log() == [("negative_reply", "edited"), ("review_fix_task", "approved")]  # 고친 뒤 승인해도 '조금 수정'


def test_revise_that_promises_compensation_is_not_used(monkeypatch):
    """고친 글에 보상 약속이 있으면(코드 검사 safe_reply) 쓰지 않고 '고치지 못했어요'라고 한다. 인사과 기록도 남기지 않는다."""
    from app.core.config import settings
    from voice import context

    donna, rid = leak_alert()
    before = repo.get("alert", f"al_{rid}")["reply_base"]
    monkeypatch.setattr(config, "agent_on", lambda name: name == "reply")
    monkeypatch.setattr(settings, "clova_studio_api_key", "test-key")
    promise = SOFT.replace("보낼게요", "보내 드릴게요")
    submit = [call("submit_reply", {"text": promise, "quoted_review_words": ["국물이 다 새서"], "menus_mentioned": [], "facts_used": []})]
    caught = judged("오늘부터 국물 메뉴는 랩을 두 번 씌워 보내 드릴게요.")  # 검토 첫 질문(보상)에서 걸린다
    monkeypatch.setattr(context, "post", FakeClova(submit, caught, submit, caught, submit, caught))  # 세 번 거절 → 물러남
    asked = donna.turn("좀 더 부드럽게 써 줘")
    assert asked["say"][0]["text"] == "지금은 고치지 못했어요." and repo.get("alert", f"al_{rid}")["reply_base"] == before
    assert hr_log() == []


def test_revise_without_agent_keeps_the_reply_and_asks_again():
    donna, rid = leak_alert()
    before = repo.get("alert", f"al_{rid}")["reply_base"]
    asked = donna.turn("좀 더 부드럽게 써 줘")
    assert asked["say"][0]["text"] == "지금은 고치지 못했어요." and repo.get("alert", f"al_{rid}")["reply_base"] == before
    assert hr_log() == [] and repo.review(rid)["reply_status"] == "proposed"  # 올리지 않았다


def test_unknown_action_on_poster_does_not_post():
    from voice.instagram import story_event
    from voice.context import load

    choongjang(at=None)
    record = story_event.save({"id": "se_test", "store_id": "s005", "date": "2026-11-17", "state": "ready", "headline": "비 오는 날",
                               "offer": "음료 1캔", "staff_task": "음료 드리기", "use_card": True, "drawn": 1, "image_url": "/x.jpg",
                               "post_id": None, "task_id": None, "created_at": "2026-11-17T09:00:00+09:00"})
    asked = story_event.decide(load("s005"), "action.revise", None, record["id"], "좀 더 밝게")
    assert asked["type"] == "ask_action" and story_event.get(record["id"])["state"] == "ready"  # 올리지 않는다


def test_instagram_caption_is_revised(chj: Choongjang, ig_on, clova_on, monkeypatch):
    ig_on(FakeGraph())
    connect(chj)
    to_instagram_step(chj)
    monkeypatch.setattr(config, "agent_on", lambda name: name == "caption")
    caption = {"body": "비 오는 날 따뜻한 들깨옹심이 한 그릇 어떠세요?", "hashtags": ["#초옹장"]}
    clova_on(FakeClova([call("submit_caption", caption)]))
    revised = chj.turn("좀 더 짧게 써 줘")
    assert revised["intent"] == "instagram.revise" and revised["say"][0]["text"] == "이렇게 고쳤어요."
    assert revised["briefing"]["step_key"] == "instagram"
    plan = repo.get("marketing_plan", "s005:2026-11-17")
    assert plan["body"] == caption["body"] and plan["sources"]["caption"] == "REVISED"
    assert hr_log() == [("instagram_post", "edited")]
    chj.turn("올려")
    assert hr_log() == [("instagram_post", "edited")]  # 고친 뒤 올려도 '조금 수정' 한 건


def test_revise_eval_conditions():
    from Harness.evals.revise_eval import REVISE_DATA, followed
    import json

    case = {"previous": "가나다라마", "check": {"shorter": True, "no_emoji": True, "no_exclaim": True, "must_not": ["정말"], "must": ["감사"]}}
    assert followed(case, "감사해요") == []
    assert followed(case, "정말 😊 가나다라마바!") == ["shorter", "no_emoji", "no_exclaim", "must_not:정말", "must:감사"]
    cases = json.loads(REVISE_DATA.read_text(encoding="utf-8"))["cases"]
    assert len({c["id"] for c in cases}) == len(cases) >= 10 and all(c["kind"] in ("AUTO", "SCHEDULED") for c in cases)
