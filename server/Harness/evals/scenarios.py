"""batch 스위트의 사례 가게. Harness/tests/fakes.make_snapshot(가상 가게 t001)을 새로 만들어 바꾼다 (fakes.py 는 고치지 않는다).

진단 사례
  d1  t001 그대로: 맛 불만 3건 모두 19시대 주문, 최근 7일 19시 주문 몰림, 19시대 근무 1명
  d2  공통점 없음: 불만 3건의 주문 시각(12·15·20시대)·메뉴(잔치국수·비빔국수·만두)·근무 인원이 서로 다르다
  d3  배달 지연: 불만 3건이 모두 비 온 날(rain_mm) 저녁 19시대 배달 주문. 위험 신호 종류 DELIVERY_DELAY
  d4  음성 보기(초옹장 s005): 정답 세트의 아쉬운 리뷰 중 같은 주제 4건을 최근 4주 금요일 저녁으로 옮긴 것 (voice_view)
기대(EXPECT): 가설(또는 고칠 점)에 들어 있어야 할 말 묶음. 묶음마다 하나 이상 나오면 맞다. d2 는 confidence low.

묶음 조율 사례 (t001, 일꾼 제안은 고정. live_eval 의 supervisor 사례와 같은 문장)
  b_menu      불만 메뉴(잔치국수 m1) 홍보 포스터                  → PROMOTES_COMPLAINED_MENU
  b_mismatch  r1 맛 불만 답글 + 같은 불만의 원인 진단            → REPLY_VS_DIAGNOSIS
  b_same      단골 c1 의 r4 답글 + c1 재주문 인사               → SAME_CUSTOMER_TWICE
  b_clean1    r4 답글 하나, b_clean2  c1 재주문 인사 하나       → 충돌 없음
"""

import datetime as dt

from Harness.spec import Proposal
from Harness.tests import fakes
from Harness.tests.fakes import NOW, at

DIAGNOSIS_CASES = ("d1", "d2", "d3", "d4")
BATCH_CASES = ("b_menu", "b_mismatch", "b_same", "b_clean1", "b_clean2")
RISK_PLAN_ID = "REVIEW_FIX:risk_001:2026-11-15"
COMPLAINT_DAYS = (dt.date(2026, 11, 12), dt.date(2026, 11, 13), dt.date(2026, 11, 14))

EXPECT = {
    "d1": {"groups": [["19시", "19", "저녁"], ["1명", "한 명", "혼자"]], "confidence": None},
    "d2": {"groups": [], "confidence": "low"},
    "d3": {"groups": [["비", "우천", "날씨"], ["19시", "19", "저녁"]], "confidence": None},
    # d4 의 주제 말은 voice_view 가 고른 주제로 채운다
    "d4": {"groups": [["금요일", "금요", "저녁"]], "confidence": None},
}
TOPIC_WORDS = {"delivery": ["배달"], "taste": ["맛", "간", "국물"], "portion": ["양"], "service": ["응대", "친절", "직원"],
               "hygiene": ["위생", "청결"], "other": []}

PLANTED = {
    "b_menu": ["PROMOTES_COMPLAINED_MENU"],
    "b_mismatch": ["REPLY_VS_DIAGNOSIS"],
    "b_same": ["SAME_CUSTOMER_TWICE"],
    "b_clean1": [],
    "b_clean2": [],
}
BATCH_PLAN_IDS = {
    "b_menu": ["POSTER:e1:2026-11-21"],
    "b_mismatch": ["REVISIT_REPLY:r1:2026-11-15", RISK_PLAN_ID],
    "b_same": ["REVISIT_REPLY:r4:2026-11-15", "REORDER_NUDGE:c1:2026-11-15"],
    "b_clean1": ["REVISIT_REPLY:r4:2026-11-15"],
    "b_clean2": ["REORDER_NUDGE:c1:2026-11-15"],
}


def snapshot(case_id: str):
    """d1·d2·d3·b_* 의 t001 스냅샷 (부를 때마다 새로)."""
    snap = fakes.make_snapshot()
    if case_id == "d2":
        _no_common_cause(snap)
    elif case_id == "d3":
        _rainy_delivery(snap)
    return snap


def _set_order(snap, order_id: str, when: dt.datetime, menu_id: str, channel: str | None = None) -> None:
    inputs = snap.inputs
    inputs.orders[:] = [o.model_copy(update={"ordered_at": when, **({"channel": channel} if channel else {})})
                        if o.order_id == order_id else o for o in inputs.orders]
    inputs.order_items[:] = [i.model_copy(update={"menu_id": menu_id}) if i.order_id == order_id else i for i in inputs.order_items]


def _no_common_cause(snap) -> None:
    for n, (day, hour, menu) in enumerate(zip(COMPLAINT_DAYS, (12, 15, 20), ("m1", "m2", "m3")), 1):
        _set_order(snap, f"ocomp{n}", at(day, hour, 40), menu, "HALL" if n == 2 else None)
    # 근무: 12일은 점심 2명, 13일은 오후 1명, 14일은 저녁 2명 (서로 다르게)
    shifts = snap.inputs.shifts
    shifts.append(shifts[0].model_copy(update={"shift_id": "s12c", "staff_key": "staffC"}))
    shifts.append(shifts[5].model_copy(update={"shift_id": "s14c", "staff_key": "staffC"}))


def _rainy_delivery(snap) -> None:
    from app.analysis.input_shapes import WeatherDay

    texts = ["비 오는 날 시켰더니 배달이 한 시간 넘게 걸렸어요", "배달이 너무 늦어서 면이 다 불었어요",
             "주문하고 한참 기다렸어요. 배달이 늦네요"]
    for n, day in enumerate(COMPLAINT_DAYS, 1):
        _set_order(snap, f"ocomp{n}", at(day, 19, 30), "m1", "BAEMIN")
    snap.inputs.weather[:] = [*snap.inputs.weather, *(WeatherDay(date=day, temp_max=9.0, temp_min=3.0, rain_mm=12.0)
                                                      for day in COMPLAINT_DAYS)]
    label = fakes.label("NEGATIVE", ["DELIVERY_DELAY"])
    changed = []
    for review in snap.reviews:
        if review.review_id in ("r1", "r2", "r3"):
            index = int(review.review_id[1]) - 1
            review = review.model_copy(update={"text": texts[index], "label": label, "platform": "BAEMIN"})
        changed.append(review)
    snap.reviews[:] = changed
    snap.inputs.reviews[:] = changed
    snap.risk_signals[:] = [risk.model_copy(update={"complaint_type": "DELIVERY_DELAY"}) for risk in snap.risk_signals]


def plan_item(snap, plan_id: str):
    return next(item for item in snap.plan.plan_items if item.plan_id == plan_id)


def fixed_proposals() -> dict[str, Proposal]:
    """일꾼 초안 (고정). Harness/live_eval.py 의 supervisor 사례와 같은 문장이다."""
    def p(plan_id, **content):
        return Proposal("fixed", plan_id, content, "AGENT", "fixed")

    return {
        "REVISIT_REPLY:r1:2026-11-15": p("REVISIT_REPLY:r1:2026-11-15", kind="REPLY", text="국물이 싱거우셨다니 죄송합니다. 간을 다시 보겠습니다."),
        "REVISIT_REPLY:r4:2026-11-15": p("REVISIT_REPLY:r4:2026-11-15", kind="REPLY", text="비빔국수 양념을 알아봐 주셔서 감사해요."),
        "REORDER_NUDGE:c1:2026-11-15": p("REORDER_NUDGE:c1:2026-11-15", kind="NUDGE", text="이번 주말엔 비빔국수 어떠세요?"),
        RISK_PLAN_ID: p(RISK_PLAN_ID, risk_id="risk_001", confidence="high", checklist=[],
                        hypotheses=[{"text": "불만 3건 모두 19시(오후 7시) 주문이고 그때 근무는 1명이에요", "evidence": ["get_orders_by_hour"]}]),
        "POSTER:e1:2026-11-21": p("POSTER:e1:2026-11-21", theme="축제", menu_ids=["m1", "m3"], reason="따끈해요.", ments=[]),
    }


# ── d4: 음성 보기 ──

VOICE_TOPICS = {"DELIVERY_DELAY": "delivery", "TASTE": "taste", "PORTION": "portion", "SERVICE": "service", "HYGIENE": "hygiene"}
D4_COUNT = 4


def voice_reviews(gold_rows: list[dict], now: dt.datetime) -> tuple[list[dict], str]:
    """정답 세트의 아쉬운 리뷰(부정·혼합) 중 가장 많은 불만 유형 하나를 골라, D4_COUNT 건을 최근 4주 금요일 저녁 7시 반으로 옮긴다."""
    from collections import Counter

    from voice.clock import iso

    pool = [case for case in gold_rows if case["gold"]["sentiment"] != "POSITIVE" and case["gold"]["complaint_types"]]
    counts = Counter(t for case in pool for t in case["gold"]["complaint_types"] if t in VOICE_TOPICS)
    if not counts:
        return [], "other"
    kind = counts.most_common(1)[0][0]
    chosen = sorted((case for case in pool if kind in case["gold"]["complaint_types"]), key=lambda c: c["case_id"])[:D4_COUNT]
    fridays = []
    day = now.date() - dt.timedelta(days=1)
    while len(fridays) < D4_COUNT:
        if day.weekday() == 4:
            fridays.append(day)
        day -= dt.timedelta(days=1)
    topic = VOICE_TOPICS[kind]
    reviews = [{"id": case["case_id"], "platform": "baemin", "rating": case.get("rating"), "order_channel": case.get("order_channel"),
                "written_at": iso(dt.datetime.combine(friday, dt.time(19, 30), tzinfo=now.tzinfo)), "text": case["text"],
                "sentiment": "negative", "topic": topic, "summary": ""} for case, friday in zip(chosen, fridays)]
    return reviews, topic


def d4_expect(topic: str) -> dict:
    return {"groups": [TOPIC_WORDS.get(topic) or [], *EXPECT["d4"]["groups"]], "confidence": None}


NOW_T001 = NOW
