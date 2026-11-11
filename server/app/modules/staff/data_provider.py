"""알바 목록과 근무 기록 가져오기. DB(지호) → 서버 → 앱으로 바로 보낸다 (분석을 거치지 않는다).

- 근무 기록은 지금 시각까지 시작한 근무만 보낸다. 목업 DB 에는 12/31 까지 근무가 미리 들어 있어서다.
- 앱에 아직 알바 화면이 없다. 영웅이 화면을 만들면 이 API 를 쓰면 된다.
"""

import datetime as dt

from app.core.seoul_time import SEOUL, now_seoul
from app.data_pipeline import read_store_db
from app.data_pipeline.db_rows_to_analysis_inputs import staff_key_of
from app.modules.staff.response_format import ShiftRecord, ShiftsResponse, StaffMember, StaffResponse


def get_staff(store_id: str) -> StaffResponse:
    staff = [
        StaffMember(staff_id=staff_key_of(row["staff_id"]), name=row["name"], hourly_wage=row["hourly_wage"])
        for row in read_store_db.read_staff(store_id)
    ]
    return StaffResponse(is_example=False, staff=staff)


def get_shifts(store_id: str, from_date: dt.date | None, to_date: dt.date | None) -> ShiftsResponse:
    """기간 안에 시작한 근무. 기간을 비우면 이번 주 월요일 ~ 오늘."""
    now = now_seoul()
    today = now.date()
    from_date = from_date or today - dt.timedelta(days=today.weekday())
    to_date = to_date or today
    since = dt.datetime.combine(from_date, dt.time(0, 0), SEOUL)
    until = min(now, dt.datetime.combine(to_date + dt.timedelta(days=1), dt.time(0, 0), SEOUL) - dt.timedelta(microseconds=1))

    staff = {row["staff_id"]: row for row in read_store_db.read_staff(store_id)}
    shifts = []
    for row in read_store_db.read_shifts(store_id, until, since=since):
        member = staff[row["staff_id"]]
        hours = (row["ends_at"] - row["starts_at"]).total_seconds() / 3600
        shifts.append(
            ShiftRecord(
                shift_id=str(row["shift_id"]),
                staff_id=staff_key_of(row["staff_id"]),
                name=member["name"],
                starts_at=row["starts_at"],
                ends_at=row["ends_at"],
                hours=round(hours, 1),
                pay=round(hours * member["hourly_wage"]),
            )
        )
    return ShiftsResponse(
        is_example=False,
        from_date=from_date,
        to_date=to_date,
        total_hours=round(sum(s.hours for s in shifts), 1),
        total_pay=sum(s.pay for s in shifts),
        shifts=shifts,
    )
