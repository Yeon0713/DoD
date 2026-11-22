"""아침 브리핑에서 사과 답글의 혜택 문장을 빼고 올리기 (Figma v0.2.1 J-10a · J-10b · J-12b, jobs/batch_ask.drop_offer_and_post).

초옹장 J 픽스처(11/17 09:02): 부정 리뷰 답글 인턴, 밤사이 '면이 불어서 왔어요' 리뷰(rv_h05)에 써 둔 답글 끝에
"다음 방문 때 음료 한 잔 서비스로 드릴게요."가 있다. "서비스 준다는 말은 빼고 올려"면 그 문장을 규칙으로 빼고 바로 올린다.
"""

import pytest

from voice import notebook, repo, width
from voice.dialog import intent_rules
from voice.jobs import batch_ask
from voice.tests.conftest import Choongjang, hr_log, walk_to

KEPT = "불어서 드시게 해 정말 죄송합니다. 다음부터 배달은 면과 국물을 따로 담아 보내 드릴게요."
OFFER = "다음 방문 때 음료 한 잔 서비스로 드릴게요."
RULE = "사과할 때 서비스 준다는 말은 하지 않기"
SAID = "서비스 준다는 말은 빼고 올려"


@pytest.fixture
def j() -> Choongjang:
    donna = Choongjang()
    assert donna.client.post("/v1/dev/fixtures", json={"fixture": "s005_choongjang_j"}).json()["store_id"] == "s005"
    return donna


def test_j10a_negative_reply_is_always_asked(j: Choongjang):
    asked = walk_to(j, "negative")
    assert asked["type"] == "ask_action" and asked["headline"] == "사과 답변을 올릴까요?"
    assert [(s["text"], s["caption"]) for s in asked["say"]] == [
        ("어젯밤 배달로 드신 손님이 면이 불어서 왔다는 리뷰를 남기셨어요.", "부정 리뷰는 꼭 여쭤보고 올려요"), ("써 둔 사과 답변을 올릴까요?", None)]
    reply = asked["cards"][0]["reply"]
    assert reply == {"text": f"{KEPT} {OFFER}", "posted_at": None, "by": "donna"}  # 'scheduled_label' 없이
    assert width.violations(asked) == []


def test_j10b_drop_offer_posts_and_records_once(j: Choongjang, monkeypatch):
    judged = []
    monkeypatch.setattr(notebook, "spawn", lambda target, *args: judged.append(args))
    walk_to(j, "negative")
    done = j.turn(SAID)
    assert done["intent"] == "action.approve" and done["type"] == "answer" and done["headline"] == "빼고 올렸어요"
    assert done["briefing"] == {"step": 3, "total": 4, "step_key": "negative"}  # 따로 보여 주고, 가만히 있으면 다음 단계로
    assert done["expects_reply"] is False
    assert [s["text"] for s in done["say"]] == ["서비스 준다는 말은 빼고 올렸어요.", "앞으로 사과할 때 서비스 준다는 말은 하지 않을게요."]
    review_card, note = done["cards"]
    # 앱은 removed 를 취소선으로 보인다
    assert review_card["reply"] == {"text": KEPT, "removed": OFFER, "posted_at": "2026-11-17T09:02:00+09:00", "by": "donna"}
    assert note == {"type": "quote", "id": "hr_note", "label": "인사과에 기록함 · 위기 대처", "text": RULE}
    assert width.violations(done) == []

    posted = repo.review("rv_h05")
    assert posted["reply_status"] == "posted" and posted["reply_text"] == KEPT and posted["reply_trigger"] == "owner_yes"
    assert [(r["agent"], r["text"], r["said"]) for r in notebook.all_rules("s005")] == [("negative_review", RULE, SAID)]
    assert judged == []  # 같은 말로 수첩 판정을 또 하지 않는다 (notebook.judge_later) → 규칙은 하나
    assert hr_log() == [("negative_reply", "edited")]

    following = j.turn(event="auto_next")
    assert following["briefing"]["step_key"] == "staff_tasks"
    j.turn("응")
    end = j.turn(event="auto_next")
    assert end["type"] == "end"
    assert ("아쉬운 리뷰 1건 사과 답변", "9:02에 고쳐서 올렸어요") in [(r["value"], r["sub"]) for r in end["cards"][0]["rows"]]  # J-12b


def test_plain_yes_is_listed_without_fixed(j: Choongjang):
    walk_to(j, "negative")
    j.turn("응, 올려")
    end = walk_to(j, "end", start="처음부터 다시")
    assert ("아쉬운 리뷰 1건 사과 답변", "9:02에 올렸어요") in [(r["value"], r["sub"]) for r in end["cards"][0]["rows"]]
    assert repo.review("rv_h05")["reply_text"] == f"{KEPT} {OFFER}" and notebook.all_rules("s005") == []


def test_split_offer():
    assert batch_ask.split_offer(f"{KEPT} {OFFER}") == (KEPT, OFFER, "서비스")
    assert batch_ask.split_offer(KEPT) == (KEPT, "", None)  # 뺄 혜택이 없다
    assert batch_ask.split_offer(OFFER) == (OFFER, "", None)  # 다 빼면 남는 글이 없다
    assert batch_ask.split_offer("죄송합니다. 쿠폰을 드릴게요! 다음엔 잘할게요.") == ("죄송합니다. 다음엔 잘할게요.", "쿠폰을 드릴게요!", "쿠폰")


def test_drop_offer_words_are_understood():
    found = intent_rules.match(SAID, "ask_action")
    assert found.name == "action.approve" and found.edits["drop_compensation"] is True
    assert intent_rules.match("쿠폰 얘기는 빼고 올려", "ask_action").edits["drop_compensation"] is True
    assert intent_rules.match("응, 올려", "ask_action").edits["drop_compensation"] is False


def test_judge_later_skips_words_already_written_as_a_rule(monkeypatch):
    judged = []
    monkeypatch.setattr(notebook, "spawn", lambda target, *args: judged.append(args))
    notebook.add("s9", "negative_review", RULE, SAID)
    notebook.judge_later("s9", "negative_reply", SAID)
    assert judged == []
    notebook.judge_later("s9", "negative_reply", "좀 더 짧게")
    assert judged == [("s9", "negative_reply", "좀 더 짧게")]
