"""할 일 종류별 시각 규칙 테스트. server/ 폴더에서 `python -m pytest` 로 실행한다."""

import datetime as dt
import json
from pathlib import Path

from app.core.seoul_time import SEOUL
from app.planner.data_shapes import CalendarReason, PlanInputs
from app.planner.priority_and_grouping import approval_priority, needs_execute_reminder
from app.planner.rule_complaint_fix import plan_complaint_fixes
from app.planner.rule_menu_order import plan_menu_orders
from app.planner.rule_poster import plan_posters
from app.planner.rule_reorder_nudge import plan_reorder_nudges
from app.planner.rule_review_reply import plan_review_replies

SAMPLE_INPUTS = Path(__file__).parent / "sample_inputs" / "demo_week_inputs.example.json"
INPUTS = PlanInputs.model_validate(json.loads(SAMPLE_INPUTS.read_text(encoding="utf-8")))
STORE = INPUTS.store
CYCLES = {cycle.customer_key: cycle for cycle in INPUTS.customer_cycles}


def kst(text: str) -> dt.datetime:
    """"2026-11-17 12:30" → 서울 시각"""
    return dt.datetime.strptime(text, "%Y-%m-%d %H:%M").replace(tzinfo=SEOUL)


def review(review_id: str):
    return next(r for r in INPUTS.reviews if r.review_id == review_id)


def by_id(items):
    return {item.plan_id: item for item in items}


# ── ① 리뷰 답글 ──


def test_complaint_review_is_answered_at_next_slot():
    item = by_id(plan_review_replies([review("rv_118")], CYCLES, STORE))["REVISIT_REPLY:rv_118:2026-11-17"]
    assert item.revisit_class == "QUICK"
    assert item.approval_request_at == item.execute_at == kst("2026-11-17 14:00")
    assert item.deadline_at == kst("2026-11-17 22:00")


def test_non_complaint_reviews_are_answered_on_saturday_of_the_same_week():
    item = by_id(plan_review_replies([review("rv_121")], CYCLES, STORE))["REVISIT_REPLY:rv_121:2026-11-21"]
    assert item.revisit_class == "BASIC"
    assert item.approval_request_at == kst("2026-11-21 10:00")
    assert item.execute_at == kst("2026-11-21 11:00")


def test_weekly_regular_follows_the_same_saturday_rule():
    item = by_id(plan_review_replies([review("rv_102")], CYCLES, STORE))["REVISIT_REPLY:rv_102:2026-11-14"]
    assert item.revisit_class == "WEEKLY"
    assert item.approval_request_at == kst("2026-11-14 10:00")


def test_review_after_saturday_approval_moves_to_next_saturday():
    saturday_evening = review("rv_109")  # 11/14(토) 19:00
    item = plan_review_replies([saturday_evening], CYCLES, STORE)[0]
    assert item.approval_request_at == kst("2026-11-21 10:00")

    sunday = review("rv_112").model_copy(update={"written_at": kst("2026-11-15 13:00")})
    assert plan_review_replies([sunday], CYCLES, STORE)[0].approval_request_at == kst("2026-11-21 10:00")


def test_review_between_ten_and_eleven_on_saturday_is_answered_this_week_at_next_slot():
    late = review("rv_121").model_copy(update={"written_at": kst("2026-11-21 10:30")})
    item = plan_review_replies([late], CYCLES, STORE)[0]
    assert item.approval_request_at == item.execute_at == kst("2026-11-21 14:00")  # 10:00 승인을 놓쳐 다음 알림 시각에 바로


def test_reply_week_starts_at_saturday_eleven():
    from app.planner.rule_review_reply import current_reply_week_start

    assert current_reply_week_start(kst("2026-11-19 15:00")) == kst("2026-11-14 11:00")  # 목요일
    assert current_reply_week_start(kst("2026-11-21 10:59")) == kst("2026-11-14 11:00")  # 토요일 11시 전
    assert current_reply_week_start(kst("2026-11-21 11:00")) == kst("2026-11-21 11:00")  # 토요일 11시
    assert current_reply_week_start(kst("2026-11-22 09:00")) == kst("2026-11-21 11:00")  # 일요일


def test_unlabeled_review_is_skipped():
    unlabeled = review("rv_121").model_copy(update={"label": None})
    assert plan_review_replies([unlabeled], CYCLES, STORE) == []


# ── 매달 단골 재주문 권유 ──


def test_monthly_regular_gets_reorder_nudge_four_weeks_after_reply_saturday():
    items = plan_reorder_nudges(INPUTS.reviews, CYCLES, STORE)
    assert [item.plan_id for item in items] == ["REORDER_NUDGE:c_m01:2026-11-21"]  # 답글 10/24(토) + 4주
    assert items[0].approval_request_at == kst("2026-11-21 10:00")
    assert items[0].execute_at == kst("2026-11-21 11:00")


# ── ② 메뉴판 ──


def test_menu_order_is_planned_whenever_tags_change_from_previous_day():
    items = by_id(plan_menu_orders(INPUTS.calendar, STORE))
    assert sorted(items) == [
        "MENU_ORDER:2026-11-18:2026-11-18",  # 계절 전환
        "MENU_ORDER:2026-11-19:2026-11-19",  # 경기
        "MENU_ORDER:2026-11-20:2026-11-20",  # 경기 끝
        "MENU_ORDER:2026-11-21:2026-11-21",  # 축제
        "MENU_ORDER:2026-11-23:2026-11-23",  # 축제 끝
    ]
    season = items["MENU_ORDER:2026-11-18:2026-11-18"]
    assert season.approval_request_at == kst("2026-11-17 14:00")
    assert season.execute_at == kst("2026-11-18 10:00")


def with_rain(calendar, day: dt.date):
    """그날 모든 시간대 칸에 비 이유를 더한 달력"""
    rain = CalendarReason(tag="WEATHER", ref_id=f"weather:{day}:RAIN", effect=-0.2)
    return [cell.model_copy(update={"reasons": [*cell.reasons, rain]}) if cell.date == day else cell for cell in calendar]


def test_weather_alone_does_not_change_the_menu_board():
    calendar = with_rain(INPUTS.calendar, dt.date(2026, 11, 16))  # 비 온 월요일, 다른 태그 없음
    items = by_id(plan_menu_orders(calendar, STORE))
    assert "MENU_ORDER:2026-11-16:2026-11-16" not in items  # 비가 왔다고 바꾸지 않는다
    assert "MENU_ORDER:2026-11-17:2026-11-17" not in items  # 비가 그쳤다고 되돌리지 않는다


def test_rain_only_day_still_counts_as_the_previous_day():
    calendar = with_rain(INPUTS.calendar, dt.date(2026, 11, 17))  # 비만 있는 화요일, 다음 날 겨울 시작
    items = by_id(plan_menu_orders(calendar, STORE))
    assert "MENU_ORDER:2026-11-17:2026-11-17" not in items
    assert items["MENU_ORDER:2026-11-18:2026-11-18"].reason_line == "계절 변화 때문에 메뉴판 순서를 바꿔요."


def test_rain_on_festival_day_is_ignored_and_only_the_festival_is_compared():
    calendar = with_rain(INPUTS.calendar, dt.date(2026, 11, 21))  # 축제 첫날(토)에 비, 둘째 날(일)은 맑음
    items = by_id(plan_menu_orders(calendar, STORE))
    assert items["MENU_ORDER:2026-11-21:2026-11-21"].reason_line == "근처 행사 때문에 메뉴판 순서를 바꿔요."
    assert "MENU_ORDER:2026-11-22:2026-11-22" not in items  # 비만 그치고 축제는 이어진다


# ── ③ 포스터 ──


def test_poster_is_planned_for_high_signal_game_and_event_only():
    items = by_id(plan_posters(INPUTS.calendar, INPUTS.events, INPUTS.games, STORE))
    assert sorted(items) == ["POSTER:event_012:2026-11-21", "POSTER:game_031:2026-11-19"]  # 야구 경기는 없음
    game = items["POSTER:game_031:2026-11-19"]
    assert game.approval_request_at == kst("2026-11-16 14:00")
    assert game.execute_at == kst("2026-11-17 10:00")
    assert game.deadline_at == kst("2026-11-19 20:00")


def test_weekend_poster_is_planned_when_weekend_has_no_event():
    calendar_without_festival = [
        cell.model_copy(update={"signal": "NORMAL", "reasons": [r for r in cell.reasons if r.tag != "EVENT"]})
        for cell in INPUTS.calendar
    ]
    items = by_id(plan_posters(calendar_without_festival, INPUTS.events, INPUTS.games, STORE))
    weekend = items["POSTER:2026-11-21:2026-11-21"]
    assert weekend.approval_request_at == kst("2026-11-18 14:00")
    assert weekend.execute_at == kst("2026-11-19 10:00")


# ── ④ 반복 불만 개선 ──


def test_complaint_fix_is_requested_at_first_afternoon_slot_after_detection():
    items = plan_complaint_fixes(INPUTS.risk_signals, STORE)
    assert [item.plan_id for item in items] == ["REVIEW_FIX:risk_004:2026-11-17"]
    assert items[0].approval_request_at == kst("2026-11-17 14:00")
    assert items[0].execute_at is None


def test_complaint_fix_includes_detection_at_exactly_two_pm():
    risk = INPUTS.risk_signals[0].model_copy(update={"detected_at": kst("2026-11-17 14:00")})
    assert plan_complaint_fixes([risk], STORE)[0].approval_request_at == kst("2026-11-17 14:00")


# ── 우선순위 ──


def test_priorities_follow_task_kind_and_execution_day():
    replies = by_id(plan_review_replies(INPUTS.reviews, CYCLES, STORE))
    menus = by_id(plan_menu_orders(INPUTS.calendar, STORE))
    fixes = plan_complaint_fixes(INPUTS.risk_signals, STORE)

    assert approval_priority(replies["REVISIT_REPLY:rv_118:2026-11-17"]) == 1  # 불만 리뷰
    assert approval_priority(fixes[0]) == 2  # 반복 불만 개선
    assert approval_priority(menus["MENU_ORDER:2026-11-18:2026-11-18"]) == 3  # 내일 실행
    assert approval_priority(replies["REVISIT_REPLY:rv_121:2026-11-21"]) == 4  # 같은 날 11시 발송


def test_execute_reminder_is_sent_only_for_separate_slot_execution():
    replies = by_id(plan_review_replies(INPUTS.reviews, CYCLES, STORE))
    menus = by_id(plan_menu_orders(INPUTS.calendar, STORE))

    assert needs_execute_reminder(menus["MENU_ORDER:2026-11-18:2026-11-18"], STORE)
    assert not needs_execute_reminder(replies["REVISIT_REPLY:rv_118:2026-11-17"], STORE)  # 승인과 실행이 같이
    assert not needs_execute_reminder(replies["REVISIT_REPLY:rv_121:2026-11-21"], STORE)  # 11시 자동 발송
