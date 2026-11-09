"""데모 주간(2026-11-16 월 ~ 11-22 일) 전체가 정답과 같은지 확인한다.

정답은 공통 문서의 '데모 주간 기대 결과'에 리뷰 답글 새 규칙을 반영한 것이다.
- 불만 리뷰는 그대로 다음 알림 시각
- 그 밖의 리뷰는 리뷰가 달린 주의 토요일 10:00 승인 요청, 11:00 발송 (토요일 10시 이후 리뷰는 다음 주)
- 매달 단골은 답글 토요일 4주 뒤 토요일에 재주문 권유

server/ 폴더에서 `python -m pytest` 로 실행한다.
"""

import datetime as dt
import json
from pathlib import Path

from app.planner.data_shapes import PlanInputs
from app.planner.make_plan import make_plan

SAMPLE_INPUTS = Path(__file__).parent / "sample_inputs" / "demo_week_inputs.example.json"
INPUTS = PlanInputs.model_validate(json.loads(SAMPLE_INPUTS.read_text(encoding="utf-8")))
WEEK_START, WEEK_END = dt.date(2026, 11, 16), dt.date(2026, 11, 22)

A, E, P, N = "APPROVAL_REQUEST", "EXECUTE_REMINDER", "PREVIEW", "NOTICE"

# (알림 시각, 알림 시간 이름, [(plan_id 또는 notice_id, 알림 종류, 우선순위), ...]) 우선순위 순서
EXPECTED_TIMELINE = [
    ("2026-11-16 10:00", "OPENING", [("WEEKLY_PREVIEW:2026-11-16", P, 4)]),
    ("2026-11-16 14:00", "AFTERNOON", [("POSTER:game_031:2026-11-19", A, 3)]),
    ("2026-11-17 10:00", "OPENING", [("POSTER:game_031:2026-11-19", E, 4)]),
    ("2026-11-17 14:00", "AFTERNOON", [
        ("REVISIT_REPLY:rv_118:2026-11-17", A, 1),
        ("REVIEW_FIX:risk_004:2026-11-17", A, 2),
        ("MENU_ORDER:2026-11-18:2026-11-18", A, 3),
    ]),
    ("2026-11-18 10:00", "OPENING", [
        ("MENU_ORDER:2026-11-18:2026-11-18", E, 4),
        ("SALES_ANOMALY:2026-11-17:LUNCH", N, 4),
    ]),
    ("2026-11-18 14:00", "AFTERNOON", [
        ("MENU_ORDER:2026-11-19:2026-11-19", A, 3),  # 기한 11/19 22:00
        ("POSTER:event_012:2026-11-21", A, 3),  # 기한 11/21 11:00
    ]),
    ("2026-11-19 10:00", "OPENING", [
        ("MENU_ORDER:2026-11-19:2026-11-19", E, 4),
        ("POSTER:event_012:2026-11-21", E, 4),
    ]),
    ("2026-11-19 14:00", "AFTERNOON", [("MENU_ORDER:2026-11-20:2026-11-20", A, 3)]),
    ("2026-11-20 10:00", "OPENING", [("MENU_ORDER:2026-11-20:2026-11-20", E, 4)]),
    ("2026-11-20 14:00", "AFTERNOON", [("MENU_ORDER:2026-11-21:2026-11-21", A, 3)]),
    ("2026-11-20 21:30", "CLOSING", [("REVISIT_REPLY:rv_131:2026-11-20", A, 1)]),
    ("2026-11-21 10:00", "OPENING", [
        ("REORDER_NUDGE:c_m01:2026-11-21", A, 4),
        ("REVISIT_REPLY:rv_109:2026-11-21", A, 4),
        ("REVISIT_REPLY:rv_112:2026-11-21", A, 4),
        ("REVISIT_REPLY:rv_121:2026-11-21", A, 4),
        ("REVISIT_REPLY:rv_126:2026-11-21", A, 4),
        ("MENU_ORDER:2026-11-21:2026-11-21", E, 4),
    ]),
    ("2026-11-22 14:00", "AFTERNOON", [("MENU_ORDER:2026-11-23:2026-11-23", A, 3)]),
]


def demo_week_timeline(result):
    timeline = []
    for batch in result.batches:
        if WEEK_START <= batch.slot_at.date() <= WEEK_END:
            entries = [(e.plan_id or e.notice_id, e.notify_kind, e.priority) for e in batch.entries]
            timeline.append((batch.slot_at.strftime("%Y-%m-%d %H:%M"), batch.slot, entries))
    return timeline


def test_demo_week_timeline_matches_expected():
    result = make_plan(INPUTS, dt.datetime.fromisoformat("2026-11-22T23:59:00+09:00"))
    assert demo_week_timeline(result) == EXPECTED_TIMELINE


def test_baseball_game_without_past_effect_never_appears():
    result = make_plan(INPUTS, dt.datetime.fromisoformat("2026-11-22T23:59:00+09:00"))
    assert all("game_028" not in item.plan_id for item in result.plan_items)


def test_review_not_yet_written_is_not_planned():
    before_complaint = make_plan(INPUTS, dt.datetime.fromisoformat("2026-11-17T12:00:00+09:00"))
    assert "REVISIT_REPLY:rv_118:2026-11-17" not in {item.plan_id for item in before_complaint.plan_items}
