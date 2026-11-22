"""충돌 찾기(conflicts.py)와 supervisor."""

from app.planner.data_shapes import BatchEntry, NotificationBatch
from Harness import trace
from Harness.conflicts import find_conflicts
from Harness.spec import Proposal
from Harness.supervisor import coordinate_batch
from Harness.tests.fakes import NOW, FakeClova, call
from Harness.tests.test_complaint_and_campaign import MENTS, NO_JANCHI

R1, R4 = "REVISIT_REPLY:r1:2026-11-15", "REVISIT_REPLY:r4:2026-11-15"
NUDGE, FIX, POSTER = "REORDER_NUDGE:c1:2026-11-15", "REVIEW_FIX:risk_001:2026-11-15", "POSTER:e1:2026-11-21"


def proposal(plan_id: str, **content) -> Proposal:
    return Proposal("test", plan_id, content, "AGENT", "run0")


PROPOSALS = {
    R1: proposal(R1, kind="REPLY", text="국물이 싱거우셨다니 죄송합니다. 간을 다시 보겠습니다."),
    R4: proposal(R4, kind="REPLY", text="비빔국수 양념을 알아봐 주셔서 감사해요."),
    NUDGE: proposal(NUDGE, kind="NUDGE", text="이번 주말엔 비빔국수 어떠세요?"),
    FIX: proposal(FIX, risk_id="risk_001", confidence="high", checklist=[],
                  hypotheses=[{"text": "저녁 7시 주문이 몰릴 때 국물 간이 흔들렸어요", "evidence": ["get_orders_by_hour"]}]),
    POSTER: proposal(POSTER, theme="축제", menu_ids=["m1", "m3"], reason="따끈해요.", ments=MENTS),
}


def test_finds_three_kinds_of_conflict(make_ctx):
    conflicts = find_conflicts(list(PROPOSALS), PROPOSALS, make_ctx(FakeClova()))
    found = {c.kind: c for c in conflicts}
    assert set(found) == {"PROMOTES_COMPLAINED_MENU", "REPLY_VS_DIAGNOSIS", "SAME_CUSTOMER_TWICE"}
    assert found["PROMOTES_COMPLAINED_MENU"].detail["menus"] == ["잔치국수"]  # 맛 불만 리뷰가 달린 주문의 메뉴
    assert found["REPLY_VS_DIAGNOSIS"].plan_ids == [FIX, R1]  # r4 는 불만이 없어 빠진다
    assert found["SAME_CUSTOMER_TWICE"].plan_ids == [R4, NUDGE]


def test_no_conflict_means_no_llm_call(make_ctx):
    fake = FakeClova()
    batch = NotificationBatch(slot_at=NOW, slot="AFTERNOON", entries=[
        BatchEntry(plan_id=R1, notify_kind="APPROVAL_REQUEST", priority=1),
        BatchEntry(plan_id=R1, notify_kind="EXECUTE_REMINDER", priority=4),
        BatchEntry(notice_id="n1", notify_kind="NOTICE", priority=4),
    ])
    result = coordinate_batch(batch, PROPOSALS, make_ctx(fake))
    assert result.source == "NONE" and result.plan_ids == [R1] and fake.requests == []


def test_supervisor_asks_worker_and_accepts_rewrite(make_ctx, frozen_clock):
    rewritten = call("submit_campaign", {
        "theme": "축제 구경 전후 든든한 한 끼", "menu_ids": ["m2", "m3"], "reason": "축제 날 든든하게 먹기 좋은 메뉴예요.",
        "ments": [MENTS[2], *NO_JANCHI],
    })
    fake = FakeClova(
        [call("get_proposal", {"plan_id": POSTER}),
         call("ask_campaign_agent", {"plan_id": POSTER, "note": "맛 불만이 열린 잔치국수는 빼 줘", "exclude_menu_ids": ["m1"]})],
        [rewritten],  # 일꾼(상황 마케팅) 재작업
        [call("submit_batch", {"headline": "축제 홍보는 잔치국수를 빼고 준비했어요", "item_notes": [], "accepted": [POSTER]})],
    )
    ctx = make_ctx(fake)
    result = coordinate_batch([POSTER, R4], PROPOSALS, ctx)
    assert result.source == "AGENT" and result.headline == "축제 홍보는 잔치국수를 빼고 준비했어요"
    assert result.proposals[POSTER].content["menu_ids"] == ["m2", "m3"]
    assert result.proposals[R4] is PROPOSALS[R4]
    assert "빼야 할 메뉴: 잔치국수" in fake.requests[1]["messages"][1]["content"]  # 일꾼이 받은 지시
    steps = trace.steps_of(ctx.run_id)
    worker = [s for s in steps if s["agent"] == "campaign_agent"]
    assert worker and all(s["parent_run_id"] == ctx.run_id for s in worker)  # supervisor 실행 아래 일꾼 실행


def test_cached_supervisor_result_keeps_proposals(make_ctx, frozen_clock, tmp_path, monkeypatch):
    """서버를 다시 켠 뒤(메모리만 빔) 디스크 캐시에서 꺼낸 supervisor 결과도 재작업 제안이 Proposal 이다 (H1)."""
    from Harness import cache

    monkeypatch.setattr(cache, "CACHE_PATH", tmp_path / "harness_cache.db")  # 파일 층 켜기
    rewritten = call("submit_campaign", {"theme": "축제 구경 전후 든든한 한 끼", "menu_ids": ["m2", "m3"],
                                         "reason": "축제 날 든든하게 먹기 좋은 메뉴예요.", "ments": [MENTS[2], *NO_JANCHI]})
    fake = FakeClova(
        [call("get_proposal", {"plan_id": POSTER}),
         call("ask_campaign_agent", {"plan_id": POSTER, "note": "잔치국수는 빼 줘", "exclude_menu_ids": ["m1"]})],
        [rewritten],
        [call("submit_batch", {"headline": "축제 홍보는 잔치국수를 빼고 준비했어요", "item_notes": [], "accepted": [POSTER]})],
    )
    first = coordinate_batch([POSTER, R4], PROPOSALS, make_ctx(fake))
    assert isinstance(first.proposals[POSTER], Proposal)
    cache.clear()  # 서버 재시작 = 메모리만 빔
    again_fake = FakeClova()
    again = coordinate_batch([POSTER, R4], PROPOSALS, make_ctx(again_fake))
    assert isinstance(again.proposals[POSTER], Proposal) and again.proposals[POSTER] == first.proposals[POSTER]
    assert again_fake.requests == []  # 디스크 캐시가 맞아 CLOVA 를 부르지 않음


def test_every_conflict_must_be_handled_and_no_forbidden_fields(make_ctx, frozen_clock):
    fake = FakeClova(
        [call("submit_batch", {"headline": "오늘 답글 두 개를 확인해 주세요", "item_notes": [], "accepted": []})],
        [call("submit_batch", {"headline": "오늘 답글 두 개를 확인해 주세요", "item_notes": [], "accepted": [], "remove": [NUDGE]})],
    )
    result = coordinate_batch([R4, NUDGE], PROPOSALS, make_ctx(fake))
    assert "처리하지 않은 충돌이 있어요: 같은 손님에게 두 번" in fake.tool_messages(1)[-1]
    assert result.source == "FALLBACK"  # 두 번째도 거절(할 수 없는 일) → 규칙 메모만
    assert result.item_notes == {NUDGE: ["같은 손님에게 답글도 함께 가요. 두 글이 겹치지 않는지 확인해 주세요"]}
    assert result.headline is None and result.proposals == {**PROPOSALS}


def test_note_handles_conflict(make_ctx, frozen_clock):
    fake = FakeClova([call("submit_batch", {"headline": "단골 손님 글 두 개가 함께 가요!",
                                            "item_notes": [{"plan_id": NUDGE, "note": "답글과 인사가 겹치지 않는지 봐 주세요"}], "accepted": []})])
    result = coordinate_batch([R4, NUDGE], PROPOSALS, make_ctx(fake))
    assert result.source == "AGENT" and result.item_notes == {NUDGE: ["답글과 인사가 겹치지 않는지 봐 주세요"]}


def test_revision_limits(make_ctx, frozen_clock):
    ask = call("ask_reply_agent", {"plan_id": NUDGE, "note": "답글과 겹치지 않게"})
    again = call("ask_reply_agent", {"plan_id": NUDGE, "note": "다른 지시로 한 번 더"})  # 같은 인자는 실행기가 먼저 막는다
    fake = FakeClova(
        [ask, again, call("ask_reply_agent", {"plan_id": FIX, "note": "x"})],
        500,  # 일꾼 재작업 실패 → 기존 물러나기도 실패 (conftest)
        # 실패한 재작업은 처리가 아니므로 메모를 함께 낸다 (H3). 이 시험이 보려는 것은 재작업 한도다
        [call("submit_batch", {"headline": "단골 손님 글을 확인해 주세요",
                               "item_notes": [{"plan_id": NUDGE, "note": "답글과 인사가 겹치지 않는지 봐 주세요"}], "accepted": []})],
    )
    coordinate_batch([R4, NUDGE, FIX], PROPOSALS, make_ctx(fake))
    assert fake.done()
    first, second, third = fake.tool_messages(2)[-3:]
    assert '"status": "failed"' in first
    assert "이미 한 번 다시 쓰게 했어요" in second
    assert "이 도구로 다시 쓸 수 없는 할 일이에요 (REVIEW_FIX)" in third


NOTE = {"plan_id": NUDGE, "note": "답글과 인사가 겹치지 않는지 봐 주세요"}
NUDGE_TEXT = "늘 찾아 주셔서 감사해요. 이번 주말엔 새콤달콤한 비빔국수 한 그릇 어떠세요?"


def test_failed_rewrite_still_needs_a_note(make_ctx, frozen_clock):
    """재작업을 시도만 하고 실패했으면 처리가 아니다. 메모 없는 제출은 거절된다 (H3)."""
    fake = FakeClova(
        [call("ask_reply_agent", {"plan_id": NUDGE, "note": "답글과 겹치지 않게"})],
        500,  # 일꾼 재작업 실패 (물러나기도 실패, conftest)
        [call("submit_batch", {"headline": "단골 손님 글을 확인해 주세요", "item_notes": [], "accepted": []})],
        [call("submit_batch", {"headline": "단골 손님 글을 확인해 주세요", "item_notes": [NOTE], "accepted": []})],
    )
    result = coordinate_batch([R4, NUDGE], PROPOSALS, make_ctx(fake))
    rejected = fake.tool_messages(3)[-1]
    assert "처리하지 않은 충돌이 있어요: 같은 손님에게 두 번" in rejected and "item_notes" in rejected
    assert result.source == "AGENT" and result.item_notes == {NUDGE: [NOTE["note"]]}
    assert result.proposals[NUDGE] is PROPOSALS[NUDGE]


def test_unaccepted_rewrite_needs_a_note(make_ctx, frozen_clock):
    """재작업은 성공했지만 accepted 에 넣지 않고 메모도 없으면 거절된다 (H3)."""
    fake = FakeClova(
        [call("ask_reply_agent", {"plan_id": NUDGE, "note": "답글과 겹치지 않게"})],
        [call("submit_reply", {"text": NUDGE_TEXT, "quoted_review_words": [], "menus_mentioned": ["비빔국수"]})],  # 일꾼 재작업
        [call("submit_batch", {"headline": "단골 손님 글을 확인해 주세요", "item_notes": [], "accepted": []})],
        [call("submit_batch", {"headline": "단골 손님 글을 확인해 주세요", "item_notes": [], "accepted": NUDGE})],  # 글자 하나도 받아 준다
    )
    result = coordinate_batch([R4, NUDGE], PROPOSALS, make_ctx(fake))
    assert "처리하지 않은 충돌이 있어요: 같은 손님에게 두 번" in fake.tool_messages(3)[-1]
    assert result.source == "AGENT" and result.proposals[NUDGE].content["text"] == NUDGE_TEXT


def test_accepted_must_be_a_list(make_ctx, frozen_clock):
    fake = FakeClova(
        [call("submit_batch", {"headline": "단골 손님 글을 확인해 주세요", "item_notes": [NOTE], "accepted": {"x": 1}})],
        [call("submit_batch", {"headline": "단골 손님 글을 확인해 주세요", "item_notes": [NOTE], "accepted": []})],
    )
    result = coordinate_batch([R4, NUDGE], PROPOSALS, make_ctx(fake))
    assert "accepted 는 할 일 id 목록이어야 해요" in fake.tool_messages(1)[-1] and result.source == "AGENT"


def test_supervisor_failure_falls_back_to_rule_notes(make_ctx, frozen_clock):
    result = coordinate_batch(list(PROPOSALS), PROPOSALS, make_ctx(FakeClova(500)))
    assert result.source == "FALLBACK" and set(result.item_notes) == {POSTER, R1, NUDGE}
    assert result.item_notes[POSTER] == ["잔치국수에 맛 불만이 열려 있어요. 홍보 메뉴를 확인해 주세요"]


def test_bad_headline_is_dropped_not_rejected(make_ctx, frozen_clock):
    fake = FakeClova([call("submit_batch", {"headline": "오늘의 알림 모음",
                                            "item_notes": [{"plan_id": NUDGE, "note": "답글과 인사가 겹치지 않는지 봐 주세요"}], "accepted": []})])
    result = coordinate_batch([R4, NUDGE], PROPOSALS, make_ctx(fake))
    assert result.source == "AGENT" and result.headline is None and fake.done()


def test_usable_headline():
    from Harness.supervisor import usable_headline

    assert usable_headline("단골 손님 글이 함께 가요!", "") == "단골 손님 글이 함께 가요!"
    assert usable_headline("메뉴를 개선하고 있습니다.", "") is None
    assert usable_headline("불만 3건을 먼저 봐", "불만 3건") is None  # '~요'로 끝나지 않음
    assert usable_headline("불만 5건이 있어요", "불만 3건") is None  # 근거 없는 숫자
