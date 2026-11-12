"""GET /api/settings 응답 모양과 PATCH /api/settings 요청 모양."""

from pydantic import BaseModel, field_validator

from app.planner.data_shapes import HHMM, DayHours, Daypart, Dayparts, Slots, StoreSettings, TimeRange, Weekday


class SettingsResponse(BaseModel):
    is_example: bool  # true 면 contracts/sample_responses 의 예시 데이터
    settings: StoreSettings


class SettingsUpdate(BaseModel):
    """PATCH 로 고칠 수 있는 값. 보낸 항목만 바뀐다."""

    slots: Slots | None = None  # 알림 가능 시각 세 개
    dayparts: Dayparts | None = None  # 점심, 저녁, 야간 시간대
    busy_dayparts: list[Daypart] | None = None  # 알림을 보내지 않는 바쁜 시간대
    # 요일별 장사 시간. 쉬는 날은 null. 일곱 요일을 모두 보낸다. 대표 장사 시간과 쉬는 날은 여기서 뽑는다
    weekly_hours: dict[Weekday, DayHours | None] | None = None
    break_time: TimeRange | None = None  # 브레이크 타임. null 을 보내면 없앤다
    work_hours: TimeRange | None = None  # 출근·퇴근 예정 시간
    extra_slots: list[HHMM] | None = None  # 더 넣은 알림 시각. 빈 목록을 보내면 모두 없앤다

    @field_validator("extra_slots")
    @classmethod
    def sort_extra_slots(cls, value: list[str] | None) -> list[str] | None:
        """같은 시각은 하나만, 이른 시각부터."""
        return sorted(set(value)) if value is not None else None

    @field_validator("busy_dayparts")
    @classmethod
    def drop_duplicate_dayparts(cls, value: list[Daypart] | None) -> list[Daypart] | None:
        """같은 시간대를 두 번 보내도 한 번만 남긴다 (보낸 순서 유지)."""
        return list(dict.fromkeys(value)) if value is not None else None
