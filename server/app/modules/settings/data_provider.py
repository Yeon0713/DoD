"""매장 설정 가져오기와 고치기.

지금은 응답 예시(settings_response.example.json)에서 시작해 서버 메모리에만 저장한다.
서버를 다시 켜면 예시 값으로 돌아간다. DB가 생기면 DB에 저장하고, 고친 뒤 계획을 다시 계산한다.
"""

from app.core.error_response import ApiError
from app.core.sample_response_loader import load_sample_response
from app.modules.settings.response_format import SettingsResponse, SettingsUpdate
from app.planner.data_shapes import StoreSettings

_current: SettingsResponse | None = None


def get_settings() -> SettingsResponse:
    global _current
    if _current is None:
        _current = SettingsResponse.model_validate(load_sample_response("settings"))
    return _current


def update_settings(update: SettingsUpdate) -> SettingsResponse:
    global _current
    current = get_settings()
    changes = update.model_dump(exclude_none=True)
    new_settings = StoreSettings.model_validate({**current.settings.model_dump(), **changes})
    _check_slots(new_settings)
    _current = current.model_copy(update={"settings": new_settings})
    return _current


def _check_slots(settings: StoreSettings) -> None:
    """알림 가능 시각은 영업시간 안에 있고, 바쁜 시간대에 걸리면 안 된다."""
    for slot_name, slot_time in settings.slots.model_dump().items():
        if not (settings.open_time <= slot_time <= settings.close_time):
            raise ApiError(
                400,
                "SLOT_OUTSIDE_OPEN_HOURS",
                f"{slot_name} 알림 시각 {slot_time} 이 영업시간({settings.open_time}~{settings.close_time}) 밖입니다.",
            )
        for daypart in settings.busy_dayparts:
            busy = getattr(settings.dayparts, daypart)
            if busy.start <= slot_time < busy.end:
                raise ApiError(
                    400,
                    "SLOT_IN_BUSY_DAYPART",
                    f"{slot_name} 알림 시각 {slot_time} 이 바쁜 시간대({daypart} {busy.start}~{busy.end})에 걸립니다.",
                )
