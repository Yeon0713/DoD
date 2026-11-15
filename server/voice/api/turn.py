"""POST /v1/turn (사장님이 말했을 때, 칩을 눌렀을 때, auto_next), GET·PATCH /v1/settings (허락)."""

from fastapi import APIRouter

from voice import repo
from voice.api.errors import store_not_found
from voice.api.schemas import SettingsPatch, TurnRequest
from voice.dialog import turn as dialog

router = APIRouter()


@router.post("/turn")
def post_turn(body: TurnRequest):
    try:
        return dialog.handle(body.model_dump())
    except dialog.StoreNotFound:
        return store_not_found()


@router.get("/settings")
def get_settings(store_id: str):
    if repo.store(store_id) is None:
        return store_not_found()
    return repo.settings(store_id)


@router.patch("/settings")
def patch_settings(body: SettingsPatch):
    if repo.store(body.store_id) is None:
        return store_not_found()
    return repo.save_settings(body.store_id, {**repo.settings(body.store_id), "negative_review_auto_reply": body.negative_review_auto_reply})
