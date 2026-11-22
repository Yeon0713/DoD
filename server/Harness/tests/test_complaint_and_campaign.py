"""② 반복 불만 원인 분석, ③ 상황 마케팅."""

from app.core import clova
from Harness.agents import campaign_agent, complaint_agent
from Harness.tests.fakes import FakeClova, call

FIX = "REVIEW_FIX:risk_001:2026-11-15"
MENU = "MENU_ORDER:2026-11-21:2026-11-21"
POSTER = "POSTER:e1:2026-11-21"


def item(snapshot, plan_id):
    return next(i for i in snapshot.plan.plan_items if i.plan_id == plan_id)


# ── ② 반복 불만 원인 분석 ──

LOOK = [call("get_risk_reviews", {}), call("get_orders_by_hour", {"date_from": "2026-11-08", "date_to": "2026-11-14"}),
        call("get_staff_shifts", {"date": "2026-11-13"})]
CHECKLIST = ["저녁 7시 국물 간 다시 보기", "저녁 피크에 잔치국수 조리 순서 점검", "저녁 근무 인원 늘릴지 검토"]


def diagnosis(text: str, evidence=("get_risk_reviews", "get_orders_by_hour"), confidence="high", checklist=CHECKLIST):
    return call("submit_diagnosis", {"hypotheses": [{"text": text, "evidence": list(evidence)}],
                                     "checklist": list(checklist), "confidence": confidence})


def test_diagnosis_from_tools(snapshot, make_ctx, frozen_clock):
    text = "불만 3건 모두 19시(오후 7시) 잔치국수 주문이고, 그때 주문이 평소의 4.4배인데 근무는 1명이에요"
    fake = FakeClova(LOOK, [diagnosis(text, evidence=("get_risk_reviews", "get_orders_by_hour", "get_staff_shifts"))])
    proposal = complaint_agent.diagnose(item(snapshot, FIX), make_ctx(fake))
    assert proposal.source == "AGENT" and proposal.task_id == FIX
    assert proposal.content["hypotheses"][0]["text"] == text and proposal.content["checklist"] == CHECKLIST
    reviews, by_hour, staff = fake.tool_messages(1)
    assert '"order_hours": {"19시(오후 7시)": 3}' in reviews and '"times_usual": 4.4' in by_hour
    assert "staffA" not in staff and '"staff": 1' in staff  # 직원 키(이름 대신)도 주지 않는다


def test_made_up_numbers_are_rejected(snapshot, make_ctx, frozen_clock):
    good = "저녁 7시 주문이 몰릴 때 국물 간이 흔들렸어요"
    fake = FakeClova(LOOK, [diagnosis("저녁 주문이 평소의 3.7배라 국물 간이 흔들렸어요")], [diagnosis(good)])
    proposal = complaint_agent.diagnose(item(snapshot, FIX), make_ctx(fake))
    assert "도구 결과에 없는 숫자를 썼어요: 3.7" in fake.tool_messages(2)[-1]
    assert proposal.content["hypotheses"][0]["text"] == good


def test_evidence_must_name_a_called_tool_and_two_rejections_fall_back(snapshot, make_ctx, frozen_clock):
    fake = FakeClova(
        [call("get_risk_reviews", {})],
        [diagnosis("저녁 7시 주문이 몰릴 때 국물 간이 흔들렸어요", evidence=("get_day_context",))],
        [diagnosis("저녁 7시 주문이 몰릴 때 국물 간이 흔들렸어요", evidence=())],
    )
    proposal = complaint_agent.diagnose(item(snapshot, FIX), make_ctx(fake))
    assert "실제로 부른 도구 이름" in fake.tool_messages(2)[-1]
    assert proposal.source == "FALLBACK" and fake.done()  # 거절 2번 → 물러나기 (지금의 이유 한 줄)
    assert proposal.content["reason_line"] == "최근 7일 동안 맛 불만이 3건 들어왔어요."


def test_low_confidence_is_allowed(snapshot, make_ctx, frozen_clock):
    fake = FakeClova([call("get_risk_reviews", {})], [diagnosis("공통점을 찾지 못했어요", evidence=(), confidence="low",
                                                                 checklist=["국물 간 확인", "면 삶는 시간 확인", "포장 상태 확인"])])
    proposal = complaint_agent.diagnose(item(snapshot, FIX), make_ctx(fake))
    assert proposal.content["confidence"] == "low"


def test_checklist_must_have_three(snapshot, make_ctx, frozen_clock):
    fake = FakeClova([diagnosis("저녁 7시에 몰려요", checklist=["하나"])], [diagnosis("저녁 7시에 몰려요", evidence=())])
    complaint_agent.diagnose(item(snapshot, FIX), make_ctx(fake))
    assert "정확히 3개" in fake.tool_messages(1)[0]


# ── ③ 상황 마케팅 ──

MENTS = [
    {"kind": "EVENT", "label": "축제 손님", "headline": "춘천 겨울 빛 축제\\n가는 길에", "line": "구경 전후로 따끈한 잔치국수 한 그릇 하세요", "menu": "잔치국수"},
    {"kind": "WEATHER", "label": "추운 날", "headline": "쌀쌀한 날엔\\n따끈한 국물", "line": "언 몸 녹이는 잔치국수 어떠세요?", "menu": "잔치국수"},
    {"kind": "MENU", "label": "곁들임", "headline": "국수엔 만두", "line": "만두 곁들여 든든하게 드세요", "menu": "만두"},
]


# 잔치국수를 뺀 문구 2개 (supervisor 가 잔치국수를 빼라고 했을 때)
NO_JANCHI = [
    dict(MENTS[0], line="구경 전후로 따끈한 국물 한 그릇 하세요", menu=""),
    dict(MENTS[1], line="언 몸 녹이는 비빔국수 어떠세요?", menu="비빔국수"),
]


def campaign(menu_ids=("m1", "m3"), reason="축제 구경 뒤 추운 저녁에 어울리는 따끈한 메뉴예요.", ments=MENTS):
    return call("submit_campaign", {"theme": "축제 구경 전후 따끈한 한 끼", "menu_ids": list(menu_ids), "reason": reason, "ments": list(ments)})


def test_task_from_plan_items(snapshot, make_ctx):
    ctx = make_ctx(FakeClova())
    assert campaign_agent.task_for_plan_item(item(snapshot, POSTER), ctx)["kind"] == "LOCAL_FESTIVAL"
    menu_task = campaign_agent.task_for_plan_item(item(snapshot, MENU), ctx)  # 메뉴판: 그날 달력 이유에서 찾는다
    assert (menu_task["tag"], menu_task["kind"], menu_task["ref_id"]) == ("EVENT", "LOCAL_FESTIVAL", "e1")


def test_campaign_happy_path(snapshot, make_ctx, frozen_clock):
    fake = FakeClova([call("get_menu_list", {}), call("get_event_detail", {}), call("get_day_context", {"date": "2026-11-21"})],
                     [campaign()])
    proposal = campaign_agent.plan_campaign(item(snapshot, POSTER), make_ctx(fake))
    assert proposal.source == "AGENT" and proposal.content["menu_ids"] == ["m1", "m3"]
    assert proposal.content["ments"][0]["headline"] == "춘천 겨울 빛 축제\n가는 길에"
    assert "춘천 겨울 빛 축제" in fake.tool_messages(1)[1]


def rejection(snapshot, make_ctx, bad) -> str:
    """잘못된 제출 하나 → 거절 이유. 이어서 올바른 제출로 끝난다."""
    fake = FakeClova([bad], [campaign()])
    proposal = campaign_agent.plan_campaign(item(snapshot, POSTER), make_ctx(fake))
    assert proposal.source == "AGENT"
    return fake.tool_messages(1)[0]


def test_campaign_checks(snapshot, make_ctx, frozen_clock):
    from Harness import cache

    cases = {
        "목록에 없는 menu_id 가 있어요: m9": campaign(menu_ids=("m9",)),
        "판매 주장(인기)": campaign(reason="축제 날 인기 메뉴라 골랐어요."),  # 비슷한 날 데이터를 보지 않았다
        "보상 약속('쿠폰')": campaign(ments=[dict(MENTS[0], line="리뷰 남기면 쿠폰 드려요"), *MENTS[1:]]),
        "가격·할인('20%')": campaign(ments=[dict(MENTS[0], line="오늘만 20% 싸게 드려요"), *MENTS[1:]]),
        "아직 필요한 것: 포스터 문구 1개": campaign(ments=MENTS[:2]),  # 2개는 확정하고 1개만 더 받는다
        "1번 문구 headline \"춘천 겨울 빛 축제 가는 길에 따끈한 국수\"(23자)를 22자 이하로": campaign(ments=[dict(MENTS[0], headline="춘천 겨울 빛 축제 가는 길에 따끈한 국수"), *MENTS[1:]]),
        "'~요.'로 끝나는 한 문장": campaign(reason="축제 날 어울리는 메뉴"),
        # 실제 CLOVA 가 낸 모양: 같은 문구 3개, 이름 event1 …
        "이미 확정한 문구와 같아요": campaign(ments=[dict(MENTS[0], label=f"축제{n}", menu=m) for n, m in enumerate(["잔치국수", "비빔국수", "만두"])]),
    }
    for expected, bad in cases.items():
        cache.clear()
        assert expected in rejection(snapshot, make_ctx, bad), expected


def test_english_label_is_filled_not_rejected(snapshot, make_ctx, frozen_clock):
    fake = FakeClova([campaign(ments=[dict(m, label=f"event{n}") for n, m in enumerate(MENTS)])])
    proposal = campaign_agent.plan_campaign(item(snapshot, POSTER), make_ctx(fake))
    assert [m["label"] for m in proposal.content["ments"]] == ["행사 손님", "날씨 메뉴", "대표 메뉴"]


def test_excluded_menu_from_supervisor(snapshot, make_ctx, frozen_clock):
    fake = FakeClova([campaign()], [campaign(menu_ids=("m2", "m3"), ments=[MENTS[2], *NO_JANCHI])])
    proposal = campaign_agent.plan_campaign(item(snapshot, POSTER), make_ctx(fake), exclude_menu_ids=["m1"], supervisor_note="잔치국수는 빼")
    assert "빼야 할 메뉴(잔치국수, m1)를 menu_ids 에서 빼 주세요" in fake.tool_messages(1)[0]
    assert proposal.content["menu_ids"] == ["m2", "m3"]
    assert "빼야 할 메뉴: 잔치국수" in fake.requests[0]["messages"][1]["content"]


def test_campaign_fallback_uses_existing_functions(snapshot, make_ctx, frozen_clock, monkeypatch):
    monkeypatch.setattr(clova, "ask", lambda *args, **kwargs: None)
    proposal = campaign_agent.plan_campaign(item(snapshot, POSTER), make_ctx(FakeClova(500)))
    assert proposal.source == "FALLBACK" and proposal.content["menu_ids"] == []
    assert len(proposal.content["ments"]) == 3  # 기존 ment.fallback 문장


def test_reason_ending_is_repaired_not_rejected(snapshot, make_ctx, frozen_clock):
    fake = FakeClova([campaign(reason="축제 날 따끈한 국물이 어울려요!")])
    proposal = campaign_agent.plan_campaign(item(snapshot, POSTER), make_ctx(fake))
    assert proposal.content["reason"] == "축제 날 따끈한 국물이 어울려요."


def test_passed_parts_are_locked_and_only_missing_part_is_asked(snapshot, make_ctx, frozen_clock):
    # 실제 CLOVA 처럼 같은 문구를 겹쳐 내면: 메뉴판과 서로 다른 문구 2개는 확정하고, 1개만 다시 받는다
    first = campaign(ments=[MENTS[0], dict(MENTS[0], label="또 축제"), MENTS[1]])
    fake = FakeClova([first], [call("submit_campaign", {"ments": [MENTS[2]]})])
    proposal = campaign_agent.plan_campaign(item(snapshot, POSTER), make_ctx(fake))
    message = fake.tool_messages(1)[-1]
    assert "확정한 것: 메뉴판(theme, menu_ids, reason), 문구 \"춘천 겨울 빛 축제 가는 길에\", 문구 \"쌀쌀한 날엔 따끈한 국물\"" in message
    assert "아직 필요한 것: 포스터 문구 1개" in message and "2번 문구의 headline" in message
    assert "확정한 부분은 다시 내지 말고" in message and "나머지는 그대로 두어" not in message
    assert proposal.source == "AGENT" and proposal.content["menu_ids"] == ["m1", "m3"]
    assert [m["kind"] for m in proposal.content["ments"]] == ["EVENT", "WEATHER", "MENU"]


# ── 캐시 키에 할 일 정체 (H8) ──


def test_campaign_cache_is_per_event(snapshot, make_ctx, frozen_clock):
    """같은 날 같은 종류 행사가 둘이면 두 번째 포스터가 첫 행사의 문구를 캐시에서 받지 않는다."""
    from app.planner.data_shapes import Basis

    first = snapshot.inputs.events[0]
    snapshot.inputs.events.append(first.model_copy(update={"event_id": "e2", "title": "춘천 겨울 빛 축제 둘째 마당"}))
    poster = item(snapshot, POSTER)
    other = poster.model_copy(update={"plan_id": "POSTER:e2:2026-11-21", "basis": Basis(kind="EVENT", ref_id="e2")})
    fake = FakeClova([campaign()], [campaign()])
    campaign_agent.plan_campaign(poster, make_ctx(fake))
    second = campaign_agent.plan_campaign(other, make_ctx(fake))
    assert len(fake.requests) == 2 and second.task_id == other.plan_id


def test_campaign_menu_and_poster_share_same_day(snapshot, make_ctx, frozen_clock):
    """같은 날·같은 상황의 메뉴판과 포스터는 캐시를 나눠 써 주제를 맞춘다 (지금 동작 유지)."""
    fake = FakeClova([campaign()])
    campaign_agent.plan_campaign(item(snapshot, POSTER), make_ctx(fake))
    campaign_agent.plan_campaign(item(snapshot, MENU), make_ctx(fake))
    assert len(fake.requests) == 1


def test_diagnosis_cache_is_per_risk(snapshot, make_ctx, frozen_clock):
    """모양이 같은 위험 신호 둘은 각자 진단하고, 결과 risk_id 도 각자 것이다."""
    from app.planner.data_shapes import Basis

    snapshot.risk_signals.append(snapshot.risk_signals[0].model_copy(update={"risk_id": "risk_002"}))
    fix = item(snapshot, FIX)
    other = fix.model_copy(update={"plan_id": "REVIEW_FIX:risk_002:2026-11-15", "basis": Basis(kind="RISK_SIGNAL", ref_id="risk_002")})
    text = "저녁 7시 주문이 몰릴 때 국물 간이 흔들렸어요"
    fake = FakeClova(LOOK, [diagnosis(text)], LOOK, [diagnosis(text)])
    first = complaint_agent.diagnose(fix, make_ctx(fake))
    second = complaint_agent.diagnose(other, make_ctx(fake))
    assert len(fake.requests) == 4
    assert first.content["risk_id"] == "risk_001" and second.content["risk_id"] == "risk_002"
