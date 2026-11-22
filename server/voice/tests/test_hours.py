"""자정 넘김 가게의 장사 시간 (V7, voice/hours.py close_at / open_at / business_day)."""

import datetime as dt
from types import SimpleNamespace

import pytest

from app.core.seoul_time import SEOUL
from voice import hours, proposals, staff
from voice.api import home
from voice.jobs import done_report, hr_batch, review_loop, staff_tasks

TUE = dt.date(2026, 11, 17)


def at(day: dt.date, hour: int, minute: int = 0) -> dt.datetime:
    return dt.datetime(day.year, day.month, day.day, hour, minute, tzinfo=SEOUL)


def store_of(days: list[dict | None]) -> dict:
    usual = next(d for d in days if d)
    return {"id": "s_night", "weekly_hours": days, "open_time": usual["open"], "close_time": usual["close"]}


NIGHT = store_of([{"open": "17:00", "close": "02:00"}] * 7)
DAY = store_of([{"open": "10:00", "close": "21:00"}] * 7)
WED = TUE + dt.timedelta(days=1)


def test_close_after_midnight_is_next_day():
    assert hours.close_at(TUE, {"open": "17:00", "close": "02:00"}) == at(WED, 2)
    assert hours.close_at(TUE, {"open": "10:00", "close": "21:00"}) == at(TUE, 21)
    assert hours.open_at(TUE, {"open": "17:00", "close": "02:00"}) == at(TUE, 17)


def test_alert_hours_for_overnight_store():
    assert review_loop.in_alert_hours(NIGHT, at(TUE, 23, 30)) is True
    assert review_loop.in_alert_hours(NIGHT, at(WED, 1, 30)) is True
    assert review_loop.in_alert_hours(NIGHT, at(WED, 3)) is False
    assert review_loop.in_alert_hours(NIGHT, at(WED, 16)) is True  # 문 열기 한 시간 전


def test_alert_hours_skip_after_day_off():
    days = [{"open": "17:00", "close": "02:00"}] * 7
    days[0] = None  # 월요일 쉼 → 화요일 새벽은 어제 연장이 아니다
    store = store_of(days)
    assert review_loop.in_alert_hours(store, at(TUE, 1)) is False
    assert review_loop.in_alert_hours(store, at(WED, 1)) is True


def test_24_00_does_not_crash():
    store = store_of([{"open": "17:00", "close": "24:00"}] * 7)
    assert hours.close_at(TUE, {"open": "17:00", "close": "24:00"}) == at(WED, 0)
    assert review_loop.in_alert_hours(store, at(TUE, 23, 59)) is True
    assert review_loop.in_alert_hours(store, at(WED, 0, 1)) is False
    assert hr_batch._due(store, at(TUE, 23, 45)) == at(WED, 0)
    assert home.store_status(store, at(TUE, 20))["detail"] == "밤 12시에 닫아요"


def test_day_store_unchanged():
    assert review_loop.in_alert_hours(DAY, at(TUE, 9)) is True
    assert review_loop.in_alert_hours(DAY, at(TUE, 21)) is False
    assert review_loop.in_alert_hours(DAY, at(WED, 1)) is False
    assert done_report._open_now(DAY, at(TUE, 20, 59)) is True
    assert done_report._open_now(DAY, at(TUE, 21)) is False
    assert hr_batch._due(DAY, at(TUE, 20, 45)) == at(TUE, 21)
    assert staff._phase_now(DAY, at(TUE, 9)) == "before_open"
    assert staff._phase_now(DAY, at(TUE, 12)) == "open"
    assert staff._phase_now(DAY, at(TUE, 21)) == "closing"
    assert home.store_status(DAY, at(TUE, 22))["state"] == "closed"


def test_other_places_for_overnight_store(monkeypatch):
    monkeypatch.setattr(proposals, "for_briefing", lambda store_id, day: [{"id": "p_1"}])
    view = SimpleNamespace(store=NIGHT, store_id="s_night")
    assert staff_tasks.unasked_today(view, at(TUE, 23, 30)) is True
    assert done_report._open_now(NIGHT, at(TUE, 23, 30)) is True
    assert done_report._open_now(NIGHT, at(WED, 1, 30)) is True
    assert staff._phase_now(NIGHT, at(TUE, 23, 30)) == "open"
    assert staff._phase_now(NIGHT, at(WED, 1)) == "open"
    assert staff._phase_now(NIGHT, at(WED, 3)) == "before_open"
    assert home.store_status(NIGHT, at(TUE, 23, 30)) == {"state": "open", "label": "영업 중", "detail": "밤 2시에 닫아요"}
    assert home.store_status(NIGHT, at(WED, 1))["state"] == "open"


def test_batch_due_uses_last_night_close():
    days = [{"open": "17:00", "close": "02:00"}] * 7
    days[2] = None  # 수요일 쉼: 수요일 01:45 는 화요일 영업의 끝
    assert hr_batch._due(store_of(days), at(WED, 1, 45)) == at(WED, 2)


def test_apply_week_allows_overnight():
    days = [{"open": "17:00", "close": "02:00"}] * 7
    assert hours.apply_week(DAY, days)["weekly_hours"] == days
    with pytest.raises(ValueError):
        hours.apply_week(DAY, [{"open": "17:00", "close": "17:00"}] * 7)
