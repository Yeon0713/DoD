"""매장 설정 가져오기와 고치기.

- 보기: DB 가게 정보(지호) + 사장님이 고친 값. 바쁜 시간대 기본값은 data_pipeline/analysis_to_plan_inputs.py 에 있다.
- 고치기: 고친 값은 서버 메모리에만 저장한다 (서버를 다시 켜면 DB 값으로 돌아간다. DB 저장은 다음 단계).
  고치면 그 가게 계산 결과를 지워서, 다음 요청 때 새 알림 시각으로 계획을 다시 만든다.
"""

from app.core.error_response import ApiError
from app.data_pipeline import read_store_db
from app.data_pipeline.analysis_to_plan_inputs import build_store_settings
from app.data_pipeline.store_snapshot_cache import get_settings_changes, save_settings_changes
from app.modules.settings.response_format import SettingsResponse, SettingsUpdate
from app.planner.data_shapes import StoreSettings

EARLIEST_BEFORE_OPEN_MINUTES = 60  # 출근 준비를 위해 문 열기 1시간 전부터 알림을 받을 수 있다 (앱 규칙과 같다)


def get_settings(store_id: str) -> SettingsResponse:
    settings = build_store_settings(read_store_db.read_store(store_id), get_settings_changes(store_id))
    return SettingsResponse(is_example=False, settings=settings)


def update_settings(store_id: str, update: SettingsUpdate) -> SettingsResponse:
    changes = update.model_dump(exclude_none=True, exclude={"allow_busy_slots"})
    if "break_time" in update.model_fields_set:
        changes["break_time"] = update.break_time.model_dump() if update.break_time else None
    if "work_hours" in update.model_fields_set:
        changes["work_hours"] = update.work_hours.model_dump() if update.work_hours else None
    merged = {**get_settings_changes(store_id), **changes}
    new_settings = build_store_settings(read_store_db.read_store(store_id), merged)
    # 사장님이 확인하고 바쁜 시간에 둔 알림은 기억해 두고 다음 저장 때도 막지 않는다 (그 시각이 그대로일 때만)
    accepted = dict(merged.get("busy_ok_slots") or {})
    if update.allow_busy_slots:
        accepted.update(new_settings.slots.model_dump())
        changes["busy_ok_slots"] = accepted
    _check_slots(new_settings, accepted)
    save_settings_changes(store_id, changes)
    return SettingsResponse(is_example=False, settings=new_settings)


def _minutes(hhmm: str) -> int:
    hour, minute = map(int, hhmm.split(":"))
    return hour * 60 + minute


def _check_slots(settings: StoreSettings, busy_ok: dict[str, str] | None = None) -> None:
    """알림 시각은 문 열기 1시간 전(출근 예정이 더 이르면 출근 시간) ~ 마감(퇴근 예정이 더 늦으면 퇴근 시간) 사이에 있고,
    바쁜 시간대에 걸리면 안 된다. 더 넣은 알림(extra_slots)은 그 사이에만 있으면 된다 (바쁜 시간에도 받을 수 있다).

    오류 메시지 맨 앞의 OPENING/AFTERNOON/CLOSING 으로 앱이 어느 칸 아래에 띄울지 정하므로 이 형식을 지킨다.
    """
    earliest = _minutes(settings.open_time) - EARLIEST_BEFORE_OPEN_MINUTES
    latest = _minutes(settings.close_time)
    if settings.work_hours:
        earliest = min(earliest, _minutes(settings.work_hours.start))
        latest = max(latest, _minutes(settings.work_hours.end))
    for extra in settings.extra_slots:
        if not (earliest <= _minutes(extra) <= latest):
            raise ApiError(400, "SLOT_OUTSIDE_OPEN_HOURS", f"EXTRA 알림 시각 {extra} 이 출근·퇴근 시간 밖입니다.")
    for slot_name, slot_time in settings.slots.model_dump().items():
        if not (earliest <= _minutes(slot_time) <= latest):
            raise ApiError(
                400,
                "SLOT_OUTSIDE_OPEN_HOURS",
                f"{slot_name} 알림 시각 {slot_time} 이 영업시간({settings.open_time}~{settings.close_time}) 밖입니다.",
            )
        if (busy_ok or {}).get(slot_name) == slot_time:
            continue  # 사장님이 바쁜 시간이어도 받겠다고 한 알림
        for daypart in settings.busy_dayparts:
            busy = getattr(settings.dayparts, daypart)
            if busy.start <= slot_time < busy.end:
                raise ApiError(
                    400,
                    "SLOT_IN_BUSY_DAYPART",
                    f"{slot_name} 알림 시각 {slot_time} 이 바쁜 시간대({daypart} {busy.start}~{busy.end})에 걸립니다.",
                )
