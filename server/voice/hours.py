"""장사 시간과 브리핑 알림 시각 (설정 탭 G-05, G-06, G-08).

가게 문서(store)의 open_time / close_time / closed_weekdays 는 네이버에서 받은 '평소' 장사 시간이다.
사장님이 요일마다 고치면 weekly_hours (월요일부터 7칸, 쉬는 날은 None) 가 생기고, 그날의 시간은 이것을 먼저 본다.
고치기 전 네이버 시간은 naver_hours 에 남겨 두어 '네이버에서 다시 불러오기'로 되돌릴 수 있게 한다.

브리핑은 사장님이 부를 때 한다. 알림은 기본 '문 열기 1시간 전'이고 사장님이 시각을 고를 수 있다 (2026-11-16 결정).
"""

import datetime as dt
from collections import Counter

from app.core.seoul_time import at_time

WEEKDAYS = ["월", "화", "수", "목", "금", "토", "일"]
NOTIFY_BEFORE = [120, 90, 60, 30]  # 알림 시각 고르기: 문 열기 몇 분 전
DEFAULT_BEFORE = 60


def minutes(hhmm: str) -> int:
    hour, minute = hhmm.split(":")
    return int(hour) * 60 + int(minute)


def hhmm(total: int) -> str:
    total = max(0, min(total, 23 * 60 + 59))
    return f"{total // 60:02d}:{total % 60:02d}"


def clock_label(text: str) -> str:
    """'09:30' → '오전 9시 30분'. 화면에 숫자로 적는 시각이라 말할 때의 '아침', '반'은 쓰지 않는다 (Figma G-08)."""
    t = minutes(text)
    hour, minute = divmod(t, 60)
    noon = "오전" if hour < 12 else "오후"
    shown = hour if hour <= 12 else hour - 12
    return f"{noon} {shown}시" + (f" {minute}분" if minute else "")


def naver_week(store: dict) -> list[dict | None]:
    """네이버에서 받은 평소 장사 시간을 요일 7칸으로."""
    if store.get("naver_hours"):
        return store["naver_hours"]
    closed = set(store.get("closed_weekdays") or [])
    return [None if d in closed else {"open": store["open_time"], "close": store["close_time"]} for d in range(7)]


def week(store: dict) -> list[dict | None]:
    """요일 7칸 (월요일부터). 쉬는 날은 None."""
    return store.get("weekly_hours") or naver_week(store)


def on(store: dict, day: dt.date) -> dict | None:
    """그날의 장사 시간 {"open", "close"}. 쉬는 날(요일 휴무, 사장님이 확인한 임시 휴무)이면 None."""
    if any(h["confirmed"] and h["date"] == day.isoformat() for h in store.get("holidays") or []):  # voice/holidays.py
        return None
    return week(store)[day.weekday()]


def _at(day: dt.date, text: str) -> dt.datetime:
    if text == "24:00":  # 24시간 가게: 다음 날 00:00
        return at_time(day + dt.timedelta(days=1), "00:00")
    return at_time(day, text)


def open_at(day: dt.date, today: dict) -> dt.datetime:
    return _at(day, today["open"])


def close_at(day: dt.date, today: dict) -> dt.datetime:
    """그날 문 닫는 시각. 닫는 시각이 여는 시각보다 이르거나 같으면 자정을 넘긴 것이라 다음 날
    (app/data_pipeline/db_rows_to_analysis_inputs.py 와 같은 규칙)."""
    close = _at(day, today["close"])
    return close if close > open_at(day, today) else close + dt.timedelta(days=1)


def business_day(store: dict, now: dt.datetime) -> tuple[dt.date, dict] | None:
    """now 가 아직 끝나지 않은 영업 (날짜, 그날 시간). 자정 넘김 가게의 새벽은 어제 영업의 연장으로 보고,
    아니면 오늘 것 (열기 전도 포함). 오늘 문을 닫았거나 쉬는 날이면 None. 어제가 쉬는 날이면 어제는 보지 않는다."""
    for day in (now.date() - dt.timedelta(days=1), now.date()):
        found = on(store, day)
        if found and now < close_at(day, found):
            return day, found
    return None


def summary(days: list[dict | None]) -> str:
    """설정 줄 오른쪽에 적을 한 줄: 모두 같으면 '10:30 ~ 20:30', 아니면 '요일마다 달라요'."""
    spans = {(d["open"], d["close"]) for d in days if d}
    if not spans:
        return "모두 쉬어요"
    if len(spans) == 1:
        open_, close = spans.pop()
        return f"{open_} ~ {close}"
    return "요일마다 달라요"


def apply_week(store: dict, days: list[dict | None]) -> dict:
    """사장님이 고친 요일별 시간을 가게 문서에 넣는다. 평소 시간(open_time/close_time)은 가장 많은 요일의 것으로."""
    if len(days) != 7:
        raise ValueError("요일 7칸이 필요해요")
    for d in days:
        if d and minutes(d["open"]) == minutes(d["close"]):  # 닫는 시각이 이르면 자정을 넘겨 닫는 것 (close_at)
            raise ValueError("여는 시간과 닫는 시간이 같아요")
    opened = [d for d in days if d]
    updated = {**store, "naver_hours": naver_week(store), "weekly_hours": days,
               "closed_weekdays": [i for i, d in enumerate(days) if not d]}
    if opened:
        open_, close = Counter((d["open"], d["close"]) for d in opened).most_common(1)[0][0]
        updated.update({"open_time": open_, "close_time": close})
    return updated


def notify_time(store: dict, settings: dict, day: dt.date | None = None) -> str | None:
    """그날 브리핑 알림 시각 'HH:MM'. 알림을 껐거나 쉬는 날이면 None. 고르지 않았으면 문 열기 1시간 전."""
    notify = settings.get("briefing_notify") or {}
    if notify.get("on") is False:
        return None
    hours = on(store, day) if day else {"open": store["open_time"]}
    if hours is None:
        return None
    return notify.get("time") or hhmm(minutes(hours["open"]) - DEFAULT_BEFORE)


def notify_view(store: dict, settings: dict) -> dict:
    """설정 탭과 G-08 이 쓰는 모양. 고르는 칸은 평소 여는 시각에서 2시간 ~ 30분 전."""
    notify = settings.get("briefing_notify") or {}
    open_at = minutes(store["open_time"])
    default = hhmm(open_at - DEFAULT_BEFORE)
    chosen = notify.get("time") or default
    options = []
    for before in NOTIFY_BEFORE:
        time = hhmm(open_at - before)
        hours, mins = divmod(before, 60)
        gap = " ".join(part for part in (f"{hours}시간" if hours else "", f"{mins}분" if mins else "") if part)
        options.append({"time": time, "label": clock_label(time), "sub": f"문 열기 {gap} 전", "is_default": before == DEFAULT_BEFORE})
    if chosen not in {o["time"] for o in options}:  # 장사 시간을 바꾸기 전에 고른 시각
        options.append({"time": chosen, "label": clock_label(chosen), "sub": "전에 고른 시각", "is_default": False})
        options.sort(key=lambda o: o["time"])
    return {"on": notify.get("on") is not False, "time": chosen, "time_label": clock_label(chosen),
            "is_default": chosen == default, "default_time": default, "options": options}


def hours_view(store: dict) -> dict:
    def days_of(days: list[dict | None]) -> list[dict]:
        return [{"weekday": i, "label": WEEKDAYS[i], "closed": d is None,
                 "open": (d or {}).get("open", store["open_time"]), "close": (d or {}).get("close", store["close_time"])}
                for i, d in enumerate(days)]

    return {"summary_label": summary(week(store)), "days": days_of(week(store)), "naver_days": days_of(naver_week(store))}
