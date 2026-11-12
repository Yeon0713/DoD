"""승인이 필요 없는 알림.

- 월요일 주간 예고: 월요일 출근 후. 이번 주 달력, 이번 주 할 일, 7일 안의 행사·경기, 계절 전환을 알린다.
  월요일이 휴무인 가게는 그 주에 처음 여는 날 출근 후에 알린다.
- 매출 이상: 달력으로 설명되지 않는 매출 이상이 있으면 다음 날 출근 후에 알린다.
"""

import datetime as dt

from app.planner.data_shapes import CalendarCell, Event, Game, NoticeItem, PlanItem, SalesAnomaly, StoreSettings
from app.planner.notification_time_helpers import KOREAN_WEEKDAYS, WEEKDAY_CODES, slot_at

DAYPART_NAMES = {"LUNCH": "점심", "DINNER": "저녁", "NIGHT": "야간"}


def make_weekly_previews(
    calendar: list[CalendarCell],
    events: list[Event],
    games: list[Game],
    plan_items: list[PlanItem],
    store: StoreSettings,
) -> list[NoticeItem]:
    schedules = {event.event_id: (event.title, event.start_at) for event in events}
    schedules |= {game.game_id: (game.title, game.start_at) for game in games}
    season_days = {cell.date for cell in calendar if any(r.tag == "SEASON" for r in cell.reasons)}
    calendar_days = {cell.date for cell in calendar}

    notices = []
    for monday in sorted({day - dt.timedelta(days=day.weekday()) for day in calendar_days}):
        sunday = monday + dt.timedelta(days=6)
        # 알리는 날: 월요일. 월요일이 휴무면 그 주에 처음 여는 날. 그 날이 달력에 없으면(이미 지난 주) 만들지 않는다
        open_days = [
            monday + dt.timedelta(days=offset)
            for offset in range(7)
            if WEEKDAY_CODES[offset] not in store.closed_weekdays
        ]
        if not open_days or open_days[0] not in calendar_days:
            continue
        preview_day = open_days[0]
        week_cells = sorted(
            (cell for cell in calendar if monday <= cell.date <= sunday), key=lambda c: c.date
        )

        # 이번 주 수요를 크게 움직이는 행사·경기 (나온 순서대로, 중복 없이)
        high_refs = []
        for cell in week_cells:
            if cell.signal != "HIGH":
                continue
            for reason in cell.reasons:
                if reason.tag in ("EVENT", "GAME") and reason.ref_id in schedules and reason.ref_id not in high_refs:
                    high_refs.append(reason.ref_id)

        # 계절이 바뀌는 날: SEASON 태그가 새로 붙은 날
        season_changes = sorted(
            day
            for day in season_days
            if monday <= day <= sunday and (day - dt.timedelta(days=1)) in calendar_days - season_days
        )

        week_plan_ids = [
            item.plan_id
            for item in plan_items
            if any(t is not None and monday <= t.date() <= sunday for t in (item.approval_request_at, item.execute_at))
        ]

        parts = [f"{KOREAN_WEEKDAYS[day.weekday()]}부터 계절이 바뀌어요" for day in season_changes]
        for ref_id in high_refs:
            title, start_at = schedules[ref_id]
            parts.append(f"{KOREAN_WEEKDAYS[start_at.date().weekday()]} {title}")
        summary = ", ".join(parts) if parts else "특별한 일정이 없어요"

        notices.append(
            NoticeItem(
                notice_id=f"WEEKLY_PREVIEW:{monday}",
                kind="WEEKLY_PREVIEW",
                slot_at=slot_at(preview_day, "OPENING", store),
                refs=[*sorted({str(cell.date) for cell in week_cells}), *high_refs, *week_plan_ids],
                text=f"이번 주 미리보기: {summary}. 이번 주 할 일은 {len(week_plan_ids)}개예요.",
            )
        )
    return notices


def make_sales_anomaly_alerts(anomalies: list[SalesAnomaly], store: StoreSettings) -> list[NoticeItem]:
    notices = []
    for anomaly in anomalies:
        if anomaly.known_reasons:  # 달력으로 설명되는 일은 알리지 않는다
            continue
        percent = round(abs(anomaly.ratio - 1) * 100)
        direction = "많았어요" if anomaly.ratio > 1 else "적었어요"
        notices.append(
            NoticeItem(
                notice_id=f"SALES_ANOMALY:{anomaly.date}:{anomaly.daypart}",
                kind="SALES_ANOMALY",
                slot_at=slot_at(anomaly.date + dt.timedelta(days=1), "OPENING", store),
                refs=[str(anomaly.date)],
                text=(
                    f"어제 {DAYPART_NAMES[anomaly.daypart]} 매출이 평소보다 {percent}% {direction}. "
                    "달력에 없던 일이에요."
                ),
            )
        )
    return notices
