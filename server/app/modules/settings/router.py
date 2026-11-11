"""매장 설정 API.

GET   /api/settings   매장 정보와 설정 보기
PATCH /api/settings   알림 가능 시각과 장사 시간대 고치기. 보낸 항목만 바뀐다.
    store_id 를 붙이면 다른 가게 (비우면 서버 설정 DEMO_STORE_ID)
"""

from fastapi import APIRouter, Depends

from app.data_pipeline.store_selection import store_id_param
from app.modules.settings.data_provider import get_settings, update_settings
from app.modules.settings.response_format import SettingsResponse, SettingsUpdate

router = APIRouter()


@router.get("", response_model=SettingsResponse, summary="매장 정보와 설정 보기")
def read_settings(store_id: str = Depends(store_id_param)):
    return get_settings(store_id)


@router.patch("", response_model=SettingsResponse, summary="알림 시각과 장사 시간대 고치기")
def change_settings(update: SettingsUpdate, store_id: str = Depends(store_id_param)):
    return update_settings(store_id, update)
