"""단일 에이전트 A (비교용): 알림 묶음 하나를 에이전트 하나가 끝낸다. 가짜 CLOVA."""

import pytest

from app.core import clova
from Harness.agents import quote_judge, reply_agent, reply_critic, single_agent
from Harness.evals import systems
from Harness.tests.fakes import FakeClova, call

R1 = "REVISIT_REPLY:r1:2026-11-15"
R4 = "REVISIT_REPLY:r4:2026-11-15"
NUDGE = "REORDER_NUDGE:c1:2026-11-15"
FIX = "REVIEW_FIX:risk_001:2026-11-15"
GOOD = "국물이 싱거우셨다니 정말 죄송합니다. 잔치국수 국물 간을 매일 다시 확인하겠습니다. 다음에는 꼭 제맛으로 드릴게요."
DIAGNOSIS_TEXT = "불만 3건 모두 19시(오후 7시) 잔치국수 주문이고, 그때 주문이 평소의 4.4배인데 근무는 1명이에요"
CHECKLIST = ["저녁 7시 국물 간 다시 보기", "저녁 피크에 잔치국수 조리 순서 점검", "저녁 근무 인원 늘릴지 검토"]
LOOK = [
    call("get_customer_pattern", {"plan_id": R1}),
    call("get_risk_reviews", {}),
    call("get_orders_by_hour", {"date_from": "2026-11-08", "date_to": "2026-11-14"}),
    call("get_staff_shifts", {"date": "2026-11-13"}),
]


def items(snapshot, *plan_ids):
    return [next(i for i in snapshot.plan.plan_items if i.plan_id == plan_id) for plan_id in plan_ids]


def reply(plan_id=R1, text=GOOD, quoted=("국물이 너무 싱거웠어요",), menus=("잔치국수",)):
    return {"plan_id": plan_id, "text": text, "quoted_review_words": list(quoted), "menus_mentioned": list(menus), "facts_used": []}


def diagnosis(text=DIAGNOSIS_TEXT, evidence=("get_risk_reviews", "get_orders_by_hour", "get_staff_shifts")):
    return {"hypotheses": [{"text": text, "evidence": list(evidence)}], "checklist": CHECKLIST, "confidence": "high"}


def submit(replies, diag=None):
    args = {"replies": list(replies)}
    if diag is not None:
        args["diagnosis"] = diag
    return [call("submit_batch_all", args)]


@pytest.fixture
def no_critic(monkeypatch):
    """B 의 LLM 검토(reply_critic, quote_judge)를 부르면 기록한다. 단일 에이전트는 부르지 않아야 한다."""
    called = []
    monkeypatch.setattr(reply_critic, "inspect", lambda *a, **k: called.append("inspect"))
    monkeypatch.setattr(quote_judge, "ask", lambda *a, **k: called.append("ask"))
    return called


def test_tools_submit_one_rejected_then_fixed(snapshot, make_ctx, frozen_clock, no_critic):
    fake = FakeClova(
        LOOK,
        submit([reply(quoted=("국물이 싱거웠어요",))], diagnosis()),  # 리뷰에 없는 말을 옮겼다 → 답글만 거절
        submit([reply()], diagnosis()),
    )
    proposals = single_agent.run_batch(items(snapshot, R1, FIX), make_ctx(fake))

    assert set(proposals) == {R1, FIX}
    assert proposals[R1].source == "AGENT" and proposals[R1].agent == "single_agent"
    assert proposals[R1].content == {"kind": "REPLY", "text": GOOD} and proposals[R1].task_id == R1
    assert proposals[FIX].source == "AGENT" and proposals[FIX].content["hypotheses"][0]["text"] == DIAGNOSIS_TEXT
    assert proposals[FIX].content["checklist"] == CHECKLIST and proposals[R1].run_id == proposals[FIX].run_id
    rejection = fake.tool_messages(2)[-1]  # 그 요청까지 쌓인 tool 메시지 중 마지막(제출 거절)
    assert rejection.startswith("거절: ") and f"[{R1}]" in rejection and "'국물이 싱거웠어요' 는 리뷰에 글자 그대로 없어요" in rejection
    assert f"[{FIX}]" not in rejection  # 통과한 진단은 이유에 넣지 않는다
    assert no_critic == [] and fake.done()  # 별도 LLM 검토 없이 끝난다

    pattern, risk_reviews, by_hour, staff = fake.tool_messages(1)
    assert "cx1" not in pattern and '"cycle"' in pattern  # 손님 키는 주지 않는다
    assert '"order_hours": {"19시(오후 7시)": 3}' in risk_reviews and '"times_usual": 4.4' in by_hour and '"staff": 1' in staff


def test_prompt_and_message_cover_the_whole_batch(snapshot, make_ctx, frozen_clock, no_critic):
    fake = FakeClova(LOOK, submit([reply()], diagnosis()))
    single_agent.run_batch(items(snapshot, R1, FIX), make_ctx(fake))
    first = fake.requests[0]
    system, user = first["messages"][0]["content"], first["messages"][1]["content"]

    assert "'테스트국수'의 사장님" in system  # 팀 답글 말투 프롬프트를 앞에 붙인다 (reply_agent 와 같게)
    assert "[제출 전에 스스로 확인]" in system and "[묶음 맞추기]" in system and "{업종}" not in system
    assert f"plan_id: {R1}" in user and f"plan_id: {FIX}" in user and "submit_batch_all 의 diagnosis 로" in user
    assert "submit_diagnosis" not in user and "cx1" not in user
    names = [tool["function"]["name"] for tool in first["tools"]]
    assert names == ["get_customer_pattern", "get_recent_same_complaints", "get_menu_list", "get_store_facts",
                     "get_risk_reviews", "get_orders_by_hour", "get_staff_shifts", "get_day_context", "submit_batch_all"]
    pattern_params = first["tools"][0]["function"]["parameters"]
    assert pattern_params["required"] == ["plan_id"]  # 답글 도구는 어느 할 일인지 plan_id 로 고른다
    assert first["toolChoice"] == "auto" and "thinking" not in first and first["maxTokens"] == 1024  # HCX-005 요청 그대로


def test_missing_item_and_wrong_plan_id_are_rejected_together(snapshot, make_ctx, frozen_clock, no_critic):
    low = {"hypotheses": [{"text": "공통점을 찾지 못했어요", "evidence": []}],
           "checklist": ["국물 간 확인", "면 삶는 시간 확인", "포장 상태 확인"], "confidence": "low"}
    fake = FakeClova(
        [call("get_customer_pattern", {"plan_id": "없는 할 일"})],
        submit([reply(), reply(plan_id="REVISIT_REPLY:r9:2026-11-15")]),  # 진단 빠짐 + 없는 할 일
        submit([reply()], low),
    )
    proposals = single_agent.run_batch(items(snapshot, R1, FIX), make_ctx(fake))
    assert "plan_id 를 이 묶음의 답글 할 일 중에서 골라 주세요" in fake.tool_messages(1)[0]
    first = fake.tool_messages(2)[-1]
    assert "이 묶음에 없는 plan_id: REVISIT_REPLY:r9:2026-11-15" in first and f"[{FIX}] diagnosis 가 빠졌어요" in first
    assert proposals[R1].source == "AGENT" and proposals[FIX].content["confidence"] == "low" and fake.done()


def test_duplicate_reply_is_rejected(snapshot, make_ctx, frozen_clock, no_critic):
    fake = FakeClova(submit([reply(), reply()]), submit([reply()]))
    proposals = single_agent.run_batch(items(snapshot, R1), make_ctx(fake))
    assert "두 번 냈어요" in fake.tool_messages(1)[0] and proposals[R1].source == "AGENT"


def test_budget_is_sum_of_b_workers_and_rejections_fall_back(snapshot, make_ctx, frozen_clock, no_critic, monkeypatch):
    task = single_agent.batch_task(items(snapshot, R1, R4, FIX), make_ctx(FakeClova()))
    budget = single_agent.batch_spec(task).budget
    assert (budget.max_steps, budget.max_rejections) == (5 + 5 + 8, 2 + 2 + 2)  # 답글 2 + 진단 1 → B 상한의 합

    fallback_text = "국물이 싱거우셨다니 죄송합니다. 국물 간을 다시 맞추겠습니다."
    monkeypatch.setattr(clova, "ask", lambda *args, **kwargs: fallback_text)  # 물러나기(기존 단일 호출)
    bad = reply(quoted=("싱거웠어요 정말",))
    fake = FakeClova(submit([bad], diagnosis()), submit([bad], diagnosis()), submit([bad], diagnosis()), submit([bad], diagnosis()))
    proposals = single_agent.run_batch(items(snapshot, R1, FIX), make_ctx(fake))
    assert fake.done()  # 거절 4번(답글 1 + 진단 1 의 거절 상한 합) → 물러나기
    assert proposals[R1].source == "FALLBACK" and proposals[R1].content["text"]
    assert proposals[FIX].source == "FALLBACK" and proposals[FIX].content["reason_line"] == "최근 7일 동안 맛 불만이 3건 들어왔어요."
    assert no_critic == []


def test_nudge_uses_existing_code_rule_without_llm_review(snapshot, make_ctx, frozen_clock, no_critic):
    remembers = "지난번에 드신 비빔국수 생각나시죠? 이번 주말에도 비빔국수 어떠세요?"
    good = "이번 주말엔 새콤달콤 비빔국수 어떠세요? 맛있게 준비해 둘게요."
    fake = FakeClova(
        submit([reply(plan_id=NUDGE, text=remembers, quoted=(), menus=("비빔국수",))]),
        submit([reply(plan_id=NUDGE, text=good, quoted=(), menus=("비빔국수",))]),
    )
    proposals = single_agent.run_batch(items(snapshot, NUDGE), make_ctx(fake))
    assert f"[{NUDGE}] 손님을 기억하는 척" in fake.tool_messages(1)[-1]  # 기존 rejection_reason (정규식)
    assert proposals[NUDGE].content == {"kind": "NUDGE", "text": good} and no_critic == []
    system = fake.requests[0]["messages"][0]["content"]
    assert "[단일 에이전트]" in system
    names = [t["function"]["name"] for t in fake.requests[0]["tools"]]
    assert "get_risk_reviews" not in names and "get_customer_pattern" in names  # 맡은 일의 도구만
    budget = single_agent.batch_spec(single_agent.batch_task(items(snapshot, NUDGE), make_ctx(FakeClova()))).budget
    assert budget == reply_agent.SPEC.budget  # 할 일 하나면 B 일꾼과 같은 예산


def test_other_task_types_are_not_taken(snapshot, make_ctx):
    with pytest.raises(ValueError, match="맡지 않는"):
        single_agent.batch_task(items(snapshot, "POSTER:e1:2026-11-21"), make_ctx(FakeClova()))


def test_system_a_is_this_module():
    a = systems.get("A")
    assert a.task("batch") is single_agent.run_batch and a.task("voice_prepare") is single_agent.prepare_voice
    assert single_agent.SINGLE_BATCH_SPEC.name == "single_agent" and single_agent.SINGLE_VOICE_SPEC.name == "voice_single_agent"
    with pytest.raises(systems.SystemUnavailable):
        a.task("coordinate")  # A 는 따로 조율하지 않는다
