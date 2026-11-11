"""GET /api/staff, GET /api/staff/shifts 응답 모양."""

import datetime as dt

from pydantic import BaseModel


class StaffMember(BaseModel):
    staff_id: str  # 예) staff_001
    name: str  # 알바 이름. 사장님만 보는 앱이라 이름을 그대로 보낸다
    hourly_wage: int  # 시급(원)


class StaffResponse(BaseModel):
    is_example: bool
    staff: list[StaffMember]


class ShiftRecord(BaseModel):
    shift_id: str
    staff_id: str
    name: str
    starts_at: dt.datetime
    ends_at: dt.datetime
    hours: float  # 일한 시간 (소수 첫째 자리)
    pay: int  # 일한 시간 × 시급 (원, 반올림)


class ShiftsResponse(BaseModel):
    is_example: bool
    from_date: dt.date
    to_date: dt.date
    total_hours: float
    total_pay: int
    shifts: list[ShiftRecord]
