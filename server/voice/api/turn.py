"""POST /v1/turn (사장님이 말했을 때, 칩을 눌렀을 때, auto_next), GET·PATCH /v1/settings (허락)."""

from fastapi import APIRouter

from voice import repo
from voice.api.errors import store_not_found
from voice.api.home import store_clock
from voice.api.schemas import SettingsPatch, TurnRequest
from voice.dialog import turn as dialog

router = APIRouter()


@router.post("/turn")
def post_turn(body: TurnRequest):
    try:
        return dialog.handle(body.model_dump())
    except dialog.StoreNotFound:
        return store_not_found()


def settings_view(store_id: str) -> dict:
    """설정 탭 (문서 16-3). 허락 하나만 바꿀 수 있고 나머지는 보여 주기만 한다."""
    store = repo.store(store_id)
    return {
        **repo.settings(store_id),
        "store": {"id": store["id"], "name": store["name"]},
        "open_time_label": store_clock(store["open_time"]),
        "close_time_label": store_clock(store["close_time"]),
        "briefing_time_label": store_clock(f"{max(0, int(store['open_time'][:2]) - 1):02d}:{store['open_time'][3:]}"),
        "platforms": [
            {"key": "naver", "name": "네이버 플레이스", "connected": True},
            {"key": "baemin", "name": "배달의민족", "connected": True},
        ],
    }


@router.get("/settings")
def get_settings(store_id: str):
    if repo.store(store_id) is None:
        return store_not_found()
    return settings_view(store_id)


@router.patch("/settings")
def patch_settings(body: SettingsPatch):
    if repo.store(body.store_id) is None:
        return store_not_found()
    repo.save_settings(body.store_id, {**repo.settings(body.store_id), "negative_review_auto_reply": body.negative_review_auto_reply})
    return settings_view(body.store_id)
