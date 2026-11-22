"""자유로운 수정 ("좀 더 부드럽게", 인사과 9장 6단계). 고친 글은 다시 묻고, 인사과에는 '조금 수정'(edited)으로 남는다.

고쳐 쓰기는 뒤에서 하고 알림으로 다시 묻는다 (감사팀 9장, jobs/revise_jobs.py): 말에는 바로 "고쳐서 알려 드릴게요"라고 답하고,
알림(revise_ready)을 열면 고친 글로 묻는다. 시험은 뒤에서 돌리지 않고 바로 돌린다 (conftest). 인사과 기록은 지시를 받은 때 남는다."""

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
    told = donna.turn("좀 더 부드럽게 써 줘")
    assert told["intent"] == "action.revise" and told["say"][0]["text"] == "네, 고쳐서 알려 드릴게요."
    revised = donna.open_notice()  # 다 고치면 알림이 온다
    assert revised["type"] == "ask_action" and revised["say"][0]["text"] == "이렇게 고쳤어요."
    assert revised["cards"][0]["reply"]["text"].startswith(SOFT) and fake.done()
    assert "좀 더 부드럽게" in fake.requests[0]["messages"][-1]["content"]  # 지시와 지난 답글을 에이전트에게 준다
    donna.turn("응, 진행해")
    assert repo.review(rid)["reply_text"].startswith(SOFT)
    assert hr_log() == [("negative_reply", "edited"), ("review_fix_task", "approved")]  # 고친 뒤 승인해도 '조금 수정'


def test_revise_that_promises_compensation_is_not_used(monkeypatch):
    """고친 글에 보상 약속이 있으면 감사팀이 되돌리고, 끝내 불합격이면 쓰지 않고 '고치지 못했어요'라고 한다.
    인사과 '조금 수정'은 지시를 받은 때 남는다 (감사팀 9-2)."""
    from app.core.config import settings
    from voice import context

    donna, rid = leak_alert()
    before = repo.get("alert", f"al_{rid}")["reply_base"]
    monkeypatch.setattr(config, "agent_on", lambda name: name == "reply")
    monkeypatch.setattr(settings, "clova_studio_api_key", "test-key")
    promise = SOFT.replace("보낼게요", "보내 드릴게요")
    submit = [call("submit_reply", {"text": promise, "quoted_review_words": ["국물이 다 새서"], "menus_mentioned": [], "facts_used": []})]
    caught = judged("오늘부터 국물 메뉴는 랩을 두 번 씌워 보내 드릴게요.")  # 검토 첫 질문(보상)에서 걸린다
    fake = FakeClova(submit, caught, submit, submit)  # 첫 제출 + 되돌림 2번 → 끝내 불합격 (같은 글의 판정은 캐시)
    monkeypatch.setattr(context, "post", fake)
    donna.turn("좀 더 부드럽게 써 줘")
    asked = donna.open_notice()
    assert asked["say"][0]["text"] == "지금은 고치지 못했어요." and repo.get("alert", f"al_{rid}")["reply_base"] == before
    assert hr_log() == [("negative_reply", "edited")] and fake.done()


def test_revise_without_agent_keeps_the_reply_and_asks_again():
    donna, rid = leak_alert()
    before = repo.get("alert", f"al_{rid}")["reply_base"]
    donna.turn("좀 더 부드럽게 써 줘")
    asked = donna.open_notice()
    assert asked["say"][0]["text"] == "지금은 고치지 못했어요." and repo.get("alert", f"al_{rid}")["reply_base"] == before
    assert repo.review(rid)["reply_status"] == "proposed"  # 올리지 않았다


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
    clova_on(FakeClova([call("submit_caption", caption)], judged()))  # 2차 감사: 메뉴·이야기 밖 이야기 없음
    told = chj.turn("좀 더 짧게 써 줘")
    assert told["intent"] == "instagram.revise" and told["say"][0]["text"] == "네, 고쳐서 알려 드릴게요."
    revised = chj.open_notice()
    assert revised["say"][0]["text"] == "이렇게 고쳤어요." and revised["briefing"]["step_key"] == "instagram"
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


def test_window_reply_revised_then_fix_dropped_does_not_promise(monkeypatch):
    """묶음 창에서 "좀 더 부드럽게"로 고친 뒤 교정 할 일을 빼면, 조치 없는 글(plain)을 같은 지시로 고쳐 올린다 (known-bugs B4)."""
    from app.core.config import settings
    from voice import context
    from voice.tests.test_hr_flow import staff_negative

    donna, rid = staff_negative()  # 부정 리뷰 답글 사원, 15:40 국물 샘 리뷰
    donna.clock("2026-11-17T16:10:00+09:00")
    donna.open_notice()
    plain = repo.review(rid)["reply_ready"]["plain"]
    monkeypatch.setattr(config, "agent_on", lambda name: name == "reply")
    monkeypatch.setattr(settings, "clova_studio_api_key", "test-key")
    soft_plain = "국물이 새서 많이 불편하셨을 텐데 정말 죄송해요. 포장을 꼼꼼히 다시 살필게요."
    plain_turns = reply_turns(soft_plain)
    plain_turns[2] = judged("포장을 꼼꼼히 다시 살필게요.")  # 고칠 점: 조치 없는 글의 다짐
    fake = FakeClova(*reply_turns(), *plain_turns)
    monkeypatch.setattr(context, "post", fake)
    donna.turn("좀 더 부드럽게 써 줘")
    assert repo.review(rid)["reply_ready"]["plain"] == plain  # 조치 없는 글은 아직 고치지 않는다
    donna.turn("두 번째는 빼고 올려")
    posted, alert = repo.review(rid), repo.get("alert", f"al_{rid}")
    assert posted["reply_status"] == "posted" and "랩을 두 번" not in posted["reply_text"]
    assert posted["reply_text"] == f"{soft_plain} {alert['compensation']}"  # 사장님이 정한 보상 문장은 고치지 않고 다시 붙인다
    asked = fake.requests[-len(plain_turns)]["messages"][-1]["content"]
    assert fake.done() and alert["reply_plain"] in asked and alert["compensation"] not in asked  # 보상 문장을 뺀 plain 을 고쳤다
    assert sorted(hr_log()) == [("negative_reply", "edited"), ("review_fix_task", "rejected")]


def test_window_reply_revise_keeps_the_owner_compensation(monkeypatch):
    """묶음 창 "좀 더 부드럽게": 사장님이 정한 보상 문장은 에이전트에 넘기지 않고, 고친 글 뒤에 그대로 다시 붙인다 (known-bugs B5).
    두 번 고치면 두 번째는 첫 번째 고친 글에서 이어 고친다."""
    from app.core.config import settings
    from voice import context
    from voice.tests.test_hr_flow import staff_negative

    donna, rid = staff_negative()
    donna.clock("2026-11-17T16:10:00+09:00")
    donna.open_notice()
    comp = repo.get("alert", f"al_{rid}")["compensation"]
    assert comp and repo.review(rid)["reply_ready"]["text"].endswith(comp)  # 써 둔 글에 보상 문장이 붙어 있다
    monkeypatch.setattr(config, "agent_on", lambda name: name == "reply")
    monkeypatch.setattr(settings, "clova_studio_api_key", "test-key")
    shorter = "국물이 새서 정말 죄송해요. 오늘부터 국물 메뉴는 랩을 두 번 씌워 보낼게요."
    fake = FakeClova(*reply_turns(), *reply_turns(shorter))
    monkeypatch.setattr(context, "post", fake)
    donna.turn("좀 더 부드럽게 써 줘")
    first = fake.requests[0]["messages"][-1]["content"]
    assert comp not in first and repo.review(rid)["reply_ready"]["text"] == f"{SOFT} {comp}"
    donna.turn("더 짧게")
    second = fake.requests[len(reply_turns())]["messages"][-1]["content"]
    assert SOFT in second and comp not in second  # 고친 글에서 이어 고친다
    donna.turn("응")
    assert fake.done() and repo.review(rid)["reply_text"] == f"{shorter} {comp}"


# ── 답글을 고쳐 쓰는 동안 저장소 락을 잡지 않는다 (2026-11-22 버그 V3) ──


def test_revise_does_not_hold_the_repo_lock(monkeypatch):
    import threading

    from voice.agents import voice_reply

    seen = {}

    def fake_revise(view, review, kind, previous, instruction, occasion=None, fix=None):
        def other():
            ok = repo._lock.acquire(timeout=0.3)
            seen["other_thread_got_lock"] = ok
            if ok:
                repo._lock.release()
        t = threading.Thread(target=other)
        t.start()
        t.join()
        return {"text": previous + " 고침", "source": "AGENT", "notes": []}

    monkeypatch.setattr(voice_reply, "revise", fake_revise)
    donna, rid = leak_alert()
    before = repo.get("alert", f"al_{rid}")
    donna.turn("좀 더 부드럽게 써 줘")
    assert donna.open_notice()["say"][0]["text"] == "이렇게 고쳤어요."
    assert seen == {"other_thread_got_lock": True}
    assert repo.get("alert", f"al_{rid}")["reply_base"] == before["reply_base"] + " 고침"


def test_revise_result_dropped_if_fallback_ran_meanwhile(monkeypatch):
    from voice.agents import voice_reply
    from voice.jobs import review_loop

    def fake_revise(view, review, kind, previous, instruction, occasion=None, fix=None):
        review_loop.fallback("s005", review["id"])  # 고쳐 쓰는 사이 25분이 되어 초안으로 남겼다
        return {"text": previous + " 고침", "source": "AGENT", "notes": []}

    monkeypatch.setattr(voice_reply, "revise", fake_revise)
    donna, rid = leak_alert()
    before = repo.get("alert", f"al_{rid}")
    donna.turn("좀 더 부드럽게 써 줘")
    after = repo.get("alert", f"al_{rid}")
    assert after["state"] == "left_draft"
    assert (after["reply_base"], after["reply_plain"]) == (before["reply_base"], before["reply_plain"])
    assert [n for n in donna.notices() if n["kind"] == "revise_ready"] == []  # 고친 글을 버리고 다시 묻지 않는다
