"""업무 수첩 (voice/notebook.py, agents/notebook_rule.py, 인사과 4-8·9장 7단계)."""

import pytest

from Harness.tests.fakes import FakeClova, call
from voice import config, hr, notebook, repo
from voice.agents import voice_reply
from voice.context import load
from voice.tests.conftest import choongjang


def rule(is_rule=True, text="이모티콘 쓰지 않기", scope="common", replaces=(), banned=(), no_emoji=True):
    return [call("submit_rule", {"is_rule": is_rule, "scope": scope, "text": text if is_rule else "", "replaces": list(replaces),
                                 "banned_words": list(banned), "no_emoji": no_emoji})]


@pytest.fixture
def judge(monkeypatch):
    from app.core.config import settings
    from voice import context

    choongjang(at=None)  # 픽스처 준비는 에이전트를 끈 채로

    def use(*turns):
        monkeypatch.setattr(config, "agent_on", lambda name: name == "notebook")
        monkeypatch.setattr(settings, "clova_studio_api_key", "test-key")
        fake = FakeClova(*turns)
        monkeypatch.setattr(context, "post", fake)
        return fake

    return use


def test_rule_is_written_after_an_edit_and_announced(judge):
    fake = judge(rule())
    hr.record("s005", "negative_reply", "rv_0412", "edited", "이모티콘은 앞으로 쓰지 마")
    [found] = notebook.all_rules("s005")
    assert found["agent"] == "common" and found["text"] == "이모티콘 쓰지 않기" and found["no_emoji"] is True and fake.done()
    assert "이모티콘은 앞으로 쓰지 마" in fake.requests[0]["messages"][-1]["content"]
    [notice] = repo.all_of("notice", "s005")
    assert notice["kind"] == "notebook" and notice["say"] == ["수첩에 적었어요. 앞으로 이모티콘 쓰지 않기를 지킬게요."]


def test_one_off_words_are_not_written(judge):
    judge(rule(is_rule=False))
    hr.record("s005", "negative_reply", "rv_0412", "edited", "이건 좀 더 부드럽게")
    assert notebook.all_rules("s005") == [] and repo.all_of("notice", "s005") == []


def test_approved_and_no_words_do_not_ask(judge):
    fake = judge()  # 부르면 실패한다 (turn 없음)
    hr.record("s005", "negative_reply", "rv_0412", "approved", "응")
    hr.record("s005", "negative_reply", "rv_0410", "rejected", None)
    assert fake.requests == []


def test_new_rule_replaces_the_old_one(judge):
    old = notebook.add("s005", "revisit", "답글은 두 문장으로 쓰기", "두 문장으로 써")
    judge(rule(text="답글은 세 문장으로 쓰기", scope="agent", replaces=[old["id"]], no_emoji=False))
    hr.record("s005", "positive_reply", "rv_0401", "edited", "앞으로 답글은 세 문장으로 써")
    assert [r["text"] for r in notebook.rules("s005", "revisit")] == ["답글은 세 문장으로 쓰기"]
    kept = repo.get(notebook.KIND, "s005:revisit")["rules"][0]
    assert kept["replaced_by"] and kept["text"] == "답글은 두 문장으로 쓰기"  # 되살릴 수 있게 남긴다


def test_unknown_replaces_id_is_rejected(judge):
    fake = judge(rule(replaces=["nb_x"]), rule())
    hr.record("s005", "negative_reply", "rv_0412", "edited", "이모티콘은 앞으로 쓰지 마")
    assert "replaces 에는" in fake.tool_messages(1)[-1] and len(notebook.all_rules("s005")) == 1


def test_empty_notebook_accepts_none_in_replaces(judge):
    """수첩이 비면 스키마의 replaces enum 은 ["none"] 뿐이라 모델이 'none' 을 적는다. 거절하지 않고 처음 한 번에 받는다."""
    fake = judge(rule(replaces=["none"], banned=["none"]))  # 거절되면 두 번째 차례가 없어 실패한다
    hr.record("s005", "negative_reply", "rv_0412", "edited", "이모티콘은 앞으로 쓰지 마")
    [found] = notebook.all_rules("s005")
    assert found["text"] == "이모티콘 쓰지 않기" and fake.done() and len(fake.requests) == 1
    assert not found.get("banned_words")  # 'none' 은 금지 낱말로 적지 않는다


def test_switch_off_stops_judging(judge, monkeypatch):
    fake = judge()
    monkeypatch.setenv("VOICE_HR", "false")
    hr.record("s005", "negative_reply", "rv_0412", "edited", "이모티콘은 앞으로 쓰지 마")
    assert fake.requests == []


def test_rules_and_examples_go_into_the_reply_prompt_and_checks():
    choongjang(at=None)
    notebook.add("s005", "common", "이모티콘 쓰지 않기", "이모티콘 쓰지 마", no_emoji=True)
    notebook.add("s005", "revisit", "'최고'라는 말 쓰지 않기", "최고라는 말 쓰지 마", banned_words=["최고"])
    repo.save_review({**repo.review("rv_0401"), "reply_text": "고소한 들깨 국물 좋아해 주셔서 고마워요."})
    hr.record("s005", "positive_reply", "rv_0401", "approved", "응")
    section = notebook.section("s005", "revisit")
    assert "이모티콘 쓰지 않기" in section and "'최고'라는 말 쓰지 않기" in section and "고소한 들깨 국물 좋아해 주셔서" in section
    assert "최고라는" not in notebook.section("s005", "negative_review")  # 담당 칸은 그 담당만
    assert notebook.checks("s005", "revisit", "최고의 국물이에요") and notebook.checks("s005", "revisit", "감사해요 😊")
    assert notebook.checks("s005", "revisit", "감사해요") is None
    view = load("s005")
    from voice.context import run_context

    prompt = voice_reply.system_prompt({"review_id": "rv_0401"}, run_context(view))
    assert prompt.endswith(section)
    assert notebook.section("s005", "field_variable").count("- ") == 1  # 공통 칸 규칙만, 예시는 답글·캡션만


def test_read_and_remove_by_words_or_number():
    from voice.tests.conftest import Choongjang

    donna = Choongjang()
    donna.client.post("/v1/dev/fixtures", json={"fixture": "s005_choongjang"})
    notebook.add("s005", "common", "이모티콘 쓰지 않기", "x", no_emoji=True)
    notebook.add("s005", "revisit", "답글은 세 문장으로 쓰기", "x")
    read = donna.turn("수첩에 뭐 적혀 있어?")
    assert read["intent"] == "notebook.read" and read["say"][0]["text"] == "업무 수첩에 규칙이 두 개 있어요."
    gone = donna.turn("이모티콘 규칙 지워")
    assert gone["say"] == [{"text": "수첩에서 '이모티콘 쓰지 않기' 규칙을 지웠어요.", "caption": None, "focus": []}]
    notebook.add("s005", "marketing", "해시태그는 다섯 개까지", "x")
    asked = donna.turn("규칙 하나 지워 줘")
    assert asked["headline"] == "어느 규칙을 지울까요?"
    done = donna.turn("두 번째 거 지워")
    assert done["headline"] == "규칙을 지웠어요" and [r["text"] for r in notebook.all_rules("s005")] == ["답글은 세 문장으로 쓰기"]


def test_unanswered_remove_question_does_not_take_a_later_undo():
    """"어느 규칙을 지울까요?"에 대답하지 않고 다른 말로 넘어가면, 그 뒤 사후 취소("두 번째 답글 지워")는 수첩 규칙을 지우지 않는다
    (2026-11-22 버그 V4)."""
    donna = choongjang()
    donna.clock("2026-11-17T16:00:00+09:00")
    notebook.add("s005", "common", "이모티콘 쓰지 않기", "x")
    notebook.add("s005", "common", "느낌표 쓰지 않기", "y")
    assert donna.turn("수첩 규칙 지워")["headline"] == "어느 규칙을 지울까요?"
    assert donna.turn("오늘 예약 몇 팀이야?")["intent"] == "question"
    undo = donna.turn("두 번째 답글 지워")
    assert undo["intent"] == "report.undo" and undo["headline"] != "규칙을 지웠어요"
    assert [r["text"] for r in notebook.all_rules("s005")] == ["이모티콘 쓰지 않기", "느낌표 쓰지 않기"]


def test_remove_question_does_not_survive_the_night():
    """어제 "어느 규칙을 지울까요?"에 대답하지 않았으면, 오늘 첫 "도나야, 두 번째 답글 지워"는 수첩 규칙을 지우지 않는다 (2026-11-22 버그 V13)."""
    from voice.tests.conftest import no_morning_tasks

    donna = choongjang()
    donna.clock("2026-11-17T16:00:00+09:00")
    notebook.add("s005", "common", "이모티콘 쓰지 않기", "x")
    notebook.add("s005", "common", "느낌표 쓰지 않기", "y")
    assert donna.turn("수첩 규칙 지워")["headline"] == "어느 규칙을 지울까요?"
    donna.clock("2026-11-18T10:00:00+09:00")
    no_morning_tasks()
    undo = donna.turn("두 번째 답글 지워", addressed=True)
    assert undo["headline"] != "규칙을 지웠어요"
    assert [r["text"] for r in notebook.all_rules("s005")] == ["이모티콘 쓰지 않기", "느낌표 쓰지 않기"]


def test_kitchen_talk_between_keeps_the_remove_question():
    donna = choongjang()
    donna.clock("2026-11-17T16:00:00+09:00")
    notebook.add("s005", "common", "이모티콘 쓰지 않기", "x")
    notebook.add("s005", "common", "느낌표 쓰지 않기", "y")
    donna.turn("수첩 규칙 지워")
    assert donna.turn("3번 테이블 치워 줘")["type"] == "ignore"
    assert donna.turn("두 번째 거 지워")["headline"] == "규칙을 지웠어요"
    assert [r["text"] for r in notebook.all_rules("s005")] == ["이모티콘 쓰지 않기"]
