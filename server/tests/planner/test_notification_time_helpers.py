"""알림 시간 계산 도우미 테스트. server/ 폴더에서 `python -m pytest` 로 실행한다."""

import datetime as dt
import json
from pathlib import Path

from app.core.seoul_time import SEOUL
from app.planner.data_shapes import StoreSettings
from app.planner.notification_time_helpers import (
    next_named_slot,
    next_slot,
    postpone_if_passed,
    saturday_of_week,
    slot_name_of,
)

SAMPLE_INPUTS = Path(__file__).parent / "sample_inputs" / "demo_week_inputs.example.json"
STORE = StoreSettings.model_validate(json.loads(SAMPLE_INPUTS.read_text(encoding="utf-8"))["store"])


def kst(text: str) -> dt.datetime:
    """"2026-11-17 12:30" → 서울 시각"""
    return dt.datetime.strptime(text, "%Y-%m-%d %H:%M").replace(tzinfo=SEOUL)


def test_next_slot_finds_the_next_slot_on_the_same_day():
    assert next_slot(kst("2026-11-17 12:30"), STORE) == kst("2026-11-17 14:00")


def test_next_slot_moves_to_next_morning_after_closing_slot():
    assert next_slot(kst("2026-11-17 21:40"), STORE) == kst("2026-11-18 10:00")


def test_next_slot_excludes_same_time_unless_asked():
    assert next_slot(kst("2026-11-17 14:00"), STORE) == kst("2026-11-17 21:30")
    assert next_slot(kst("2026-11-17 14:00"), STORE, include_same_time=True) == kst("2026-11-17 14:00")


def test_next_slot_skips_closed_weekdays():
    store = STORE.model_copy(update={"closed_weekdays": ["WED"]})
    assert next_slot(kst("2026-11-17 21:40"), store) == kst("2026-11-19 10:00")


def test_next_named_slot_finds_first_afternoon_slot():
    assert next_named_slot(kst("2026-11-17 13:50"), "AFTERNOON", STORE) == kst("2026-11-17 14:00")
    assert next_named_slot(kst("2026-11-17 15:00"), "AFTERNOON", STORE) == kst("2026-11-18 14:00")


def test_slot_name_of_recognizes_slot_times_only():
    assert slot_name_of(kst("2026-11-17 10:00"), STORE) == "OPENING"
    assert slot_name_of(kst("2026-11-17 21:30"), STORE) == "CLOSING"
    assert slot_name_of(kst("2026-11-21 11:00"), STORE) is None


def test_postpone_if_passed_moves_past_approval_to_next_slot():
    assert postpone_if_passed(kst("2026-11-16 14:00"), kst("2026-11-15 22:30"), STORE) == kst("2026-11-16 14:00")
    assert postpone_if_passed(kst("2026-11-16 14:00"), kst("2026-11-16 15:00"), STORE) == kst("2026-11-16 21:30")


def test_saturday_of_week_uses_monday_to_sunday_weeks():
    assert saturday_of_week(dt.date(2026, 11, 16)) == dt.date(2026, 11, 21)  # 월요일
    assert saturday_of_week(dt.date(2026, 11, 21)) == dt.date(2026, 11, 21)  # 토요일
    assert saturday_of_week(dt.date(2026, 11, 22)) == dt.date(2026, 11, 21)  # 일요일은 하루 전 토요일
