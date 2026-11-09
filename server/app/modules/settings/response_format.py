"""GET /api/settings 응답 모양과 PATCH /api/settings 요청 모양."""

from pydantic import BaseModel

from app.planner.data_shapes import Daypart, Dayparts, Slots, StoreSettings


class SettingsResponse(BaseModel):
    is_example: bool  # true 면 contracts/sample_responses 의 예시 데이터
    settings: StoreSettings


class SettingsUpdate(BaseModel):
    """PATCH 로 고칠 수 있는 값. 보낸 항목만 바뀐다."""

    slots: Slots | None = None  # 알림 가능 시각 세 개
    dayparts: Dayparts | None = None  # 점심, 저녁, 야간 시간대
    busy_dayparts: list[Daypart] | None = None  # 알림을 보내지 않는 바쁜 시간대
