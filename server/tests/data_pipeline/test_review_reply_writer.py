"""CLOVA X 답글 초안 테스트. 진짜 CLOVA 를 부르지 않고 가짜 응답을 넣는다."""

import datetime as dt

import httpx

from app.core.config import settings
from app.core.seoul_time import SEOUL
from app.planner.data_shapes import Basis, PlanItem, Review, ReviewLabel
from app.review_reply_writer import write_reply_with_clova as writer

STORE = {"store_id": "s_test", "name": "테스트국수", "category": "국수"}  # 테스트용 가짜 가게
MENUS = ["잔치국수", "칼국수", "김밥"]
AT = dt.datetime(2026, 11, 12, 12, 0, tzinfo=SEOUL)

REVIEW = Review(  # 테스트용 가짜 리뷰
    review_id="rv_900",
    platform="BAEMIN",
    written_at=AT,
    rating=2,
    text="배달이 50분 걸렸어요. 010-1234-5678 로 연락 주세요",
    customer_key="c_test",
    label=ReviewLabel(
        sentiment="NEGATIVE", complaint_types=["DELIVERY_DELAY"], complaint_groups=["DELIVERY"],
        is_quick=True, labeler="RULE", labeled_at=AT,
    ),
)
ITEM = PlanItem(
    plan_id="REVISIT_REPLY:rv_900:2026-11-12", task_type="REVISIT_REPLY", revisit_class="QUICK",
    basis=Basis(kind="REVIEW", ref_id="rv_900"), target_date=AT.date(), approval_request_at=AT,
    execute_at=AT, deadline_at=AT, reason_line="불만이 담긴 리뷰예요.", planned_at=AT,
)


def fake_post(*answers: str):
    """부를 때마다 answers 를 하나씩 답한다. 보낸 요청은 calls 에 남긴다."""
    calls = []

    def post(*args, **kwargs):
        calls.append(kwargs["json"])
        return httpx.Response(200, json={"result": {"message": {"content": answers[min(len(calls), len(answers)) - 1]}}})

    post.calls = calls
    return post


def test_clean_answer_joins_lines_and_removes_prefix():
    assert writer.clean_answer('답글: "늦어서 죄송합니다.\n다음엔 빨리 보내겠습니다."') == "늦어서 죄송합니다. 다음엔 빨리 보내겠습니다."


def test_is_usable_rejects_promises_made_up_facts_and_blanks():
    assert writer.is_usable("늦어서 정말 죄송합니다. 조리 순서를 다시 점검하겠습니다.")
    assert not writer.is_usable("죄송합니다. 다음 주문 때 서비스로 김밥을 드릴게요.")
    assert not writer.is_usable("죄송합니다. 그때 주먹밥 그냥 내드릴게요.")
    assert not writer.is_usable("국내산 콩으로 정성껏 만든 콩국수예요. 감사합니다.")
    assert not writer.is_usable("다음에 오시면 꼭 주먹밥 함께 챙겨드릴게요. 죄송합니다.")
    assert not writer.is_usable("콩을 갈아 만든 국물이 비결이에요. 감사합니다.")
    assert not writer.is_usable("[손님 이름]님 감사합니다. 또 오세요.")
    assert not writer.is_usable("감사")  # 너무 짧다


def test_is_usable_rejects_pretending_to_remember_the_customer():
    assert not writer.is_usable("지난 방문 때 칼국수를 맛있게 드셨던 기억이 나네요! 또 오세요.")
    assert not writer.is_usable("지난번에 드신 김밥 생각나서 연락드려요. 또 오세요.")
    assert writer.is_usable("늘 저희 가게를 찾아 주셔서 감사해요. 이번 주말엔 칼국수 어떠세요?", MENUS)


def test_nudge_message_does_not_send_past_review():
    message = writer.nudge_message(MENUS)
    assert "칼국수" in message and "오늘 날짜" in message
    assert "리뷰" not in message


def test_nudge_must_mention_a_real_menu():
    assert writer.is_usable("이번 주말에 따끈한 칼국수 한 그릇 어떠세요?", MENUS)
    assert not writer.is_usable("이번 주말에 따끈한 우동 한 그릇 어떠세요?", MENUS)


def test_write_one_masks_phone_and_sends_review_facts(monkeypatch):
    monkeypatch.setattr(settings, "clova_studio_api_key", "test-key")
    post = fake_post("오래 기다리시게 해서 죄송합니다. 배달 순서를 다시 점검하겠습니다.")
    assert writer.write_one(ITEM, REVIEW, STORE, MENUS, post=post).startswith("오래 기다리시게")
    sent = post.calls[0]["messages"]
    system, user = sent[0]["content"][0]["text"], sent[1]["content"][0]["text"]
    assert "테스트국수" in system and "{가게이름}" not in system
    assert "배달 지연" in user and "별점: 2점" in user and "오늘 날짜" in user
    assert "1234-5678" not in user  # 전화번호는 가려서 보낸다


def test_write_one_retries_once_after_a_bad_answer(monkeypatch):
    monkeypatch.setattr(settings, "clova_studio_api_key", "test-key")
    post = fake_post("죄송합니다. 다음에 무료로 드릴게요.", "죄송합니다. 배달 순서를 꼭 다시 점검하겠습니다.")
    assert writer.write_one(ITEM, REVIEW, STORE, MENUS, post=post) == "죄송합니다. 배달 순서를 꼭 다시 점검하겠습니다."
    assert len(post.calls) == 2
    bad = fake_post("무료로 드릴게요. 죄송합니다.")
    assert writer.write_one(ITEM, REVIEW, STORE, MENUS, post=bad) is None


def test_write_drafts_without_key_returns_nothing(monkeypatch):
    monkeypatch.setattr(settings, "clova_studio_api_key", "")
    writer.forget_all()
    assert writer.write_drafts([ITEM], {"rv_900": REVIEW}, STORE, MENUS) == {}


def test_write_drafts_remembers_each_review(monkeypatch):
    monkeypatch.setattr(settings, "clova_studio_api_key", "test-key")
    writer.forget_all()
    calls = []

    def fake_write_one(item, review, store, menus):
        calls.append(item.plan_id)
        return "오래 기다리시게 해서 죄송합니다. 꼭 다시 점검하겠습니다."

    monkeypatch.setattr(writer, "write_one", fake_write_one)
    first = writer.write_drafts([ITEM], {"rv_900": REVIEW}, STORE, MENUS)
    second = writer.write_drafts([ITEM], {"rv_900": REVIEW}, STORE, MENUS)
    assert first == second == {ITEM.plan_id: "오래 기다리시게 해서 죄송합니다. 꼭 다시 점검하겠습니다."}
    assert calls == [ITEM.plan_id]  # 두 번째는 기억한 값을 쓴다
    writer.forget_all()
