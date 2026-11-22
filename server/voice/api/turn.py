"""POST /v1/turn (사장님이 말했을 때, auto_next, 알림 열기), GET·PATCH /v1/settings (허락, 브리핑 알림, 장사 시간, 보상 문장)."""

import re

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from voice import hours, repo, staff
from voice.api.errors import store_not_found
from voice.api.home import store_clock
from voice.api.schemas import SettingsPatch, TurnRequest
from voice.dialog import turn as dialog
from app.review_reply_writer.write_reply_with_clova import PLACEHOLDER_RE
from voice.instagram import posts
from voice.jobs import cause, queue

router = APIRouter()


@router.post("/turn")
def post_turn(body: TurnRequest):
    try:
        return dialog.handle(body.model_dump())
    except dialog.StoreNotFound:
        return store_not_found()


def settings_view(store_id: str) -> dict:
    """설정 탭 (Figma v0.2.1 G-05 ~ G-08). 사장님이 바꿀 수 있는 것: 브리핑 알림, 장사 시간, 보상 문장.
    "아쉬운 리뷰에 바로 답하기"는 없앴다. 부정 리뷰 답글 직급이 정한다 (voice/hr.py, 인사과 4-a).

    브리핑은 사장님이 부를 때 한다. 알림은 기본 문 열기 1시간 전이고 사장님이 고른다 (briefing_notify).
    알바생 수는 알바생 화면에 들어온 사람 수 (없으면 null, 앱은 줄을 숨긴다).
    """
    store = repo.store(store_id)
    saved = repo.settings(store_id)
    notify = hours.notify_view(store, saved)
    return {
        "store": {"id": store["id"], "name": store["name"]},
        "open_time_label": store_clock(store["open_time"]),
        "close_time_label": store_clock(store["close_time"]),
        "briefing_time_label": notify["time_label"],  # v0.2.0 앱이 쓰던 칸. 이제 알림 시각과 같다
        "briefing_notify": notify,
        "hours": hours.hours_view(store),
        "account": {"store_name": store["name"], "address": store.get("address")},
        "staff_count": staff.joined_count(store_id) or None,
        "compensation": compensation_view(saved),
        "story_event": story_event_view(saved),
        "platforms": [
            {"key": "naver", "name": "네이버 플레이스", "connected": True},
            {"key": "baemin", "name": "배달의민족", "connected": True},
            {"key": "instagram", "name": "인스타그램", "connected": posts.connection(store_id)["connected"]},
        ],
    }


def compensation_view(saved: dict) -> dict:
    """아쉬운 리뷰 답글에 붙일 사장님이 정한 보상 한 문장 (불만 종류마다, 없으면 null)."""
    presets = saved.get("compensation") or {}
    return {key: presets.get(key) for key in cause.COMPENSATION_KEYS}


STORY_EVENT_KEYS = ("headline", "offer", "staff_task")


def story_event_view(saved: dict) -> dict:
    """비 오는 날 스토리 이벤트에 쓸 사장님이 정한 문장 (없으면 null). offer 와 staff_task 가 있어야 도나가 제안한다."""
    found = saved.get("story_event") or {}
    return {key: found.get(key) for key in STORY_EVENT_KEYS}


def check_compensation(text: str | None) -> str | None:
    """보상 문장 검사: 한 문장, 6 ~ 60자, 빈칸([메뉴] 같은 것) 없이. 문제가 없으면 None."""
    if text is None:
        return None
    body = text.strip()
    if not 6 <= len(body) <= 60:
        return "보상 문장은 6자에서 60자 사이로 적어 주세요."
    if PLACEHOLDER_RE.search(body):
        return "빈칸을 채워 주세요."
    if len([part for part in re.split(r"[.!?]", body) if part.strip()]) > 1:
        return "보상 문장은 한 문장으로 적어 주세요."
    return None


@router.get("/settings")
def get_settings(store_id: str):
    if repo.store(store_id) is None:
        return store_not_found()
    return settings_view(store_id)


@router.patch("/settings")
def patch_settings(body: SettingsPatch):
    store = repo.store(body.store_id)
    if store is None:
        return store_not_found()
    sent = body.model_fields_set
    saved = dict(repo.settings(body.store_id))
    if body.briefing_notify is not None:
        notify = dict(saved.get("briefing_notify") or {})
        if "on" in body.briefing_notify.model_fields_set:
            notify["on"] = body.briefing_notify.on is not False
        if "time" in body.briefing_notify.model_fields_set:
            notify["time"] = body.briefing_notify.time  # null = 기본(문 열기 1시간 전)으로
        saved["briefing_notify"] = notify
    if body.compensation is not None:
        presets = dict(saved.get("compensation") or {})
        for key, text in body.compensation.items():
            if key not in cause.COMPENSATION_KEYS:
                return JSONResponse(status_code=400, content={"error": {"code": "bad_compensation", "message": f"모르는 불만 종류예요: {key}"}})
            problem = check_compensation(text)
            if problem:
                return JSONResponse(status_code=400, content={"error": {"code": "bad_compensation", "message": problem}})
            presets[key] = text.strip() if text else None
        saved["compensation"] = presets
    if body.story_event is not None:
        event = dict(saved.get("story_event") or {})
        for key, text in body.story_event.items():
            if key not in STORY_EVENT_KEYS:
                return JSONResponse(status_code=400, content={"error": {"code": "bad_story_event", "message": f"모르는 칸이에요: {key}"}})
            body_text = (text or "").strip()
            if body_text and (len(body_text) > 60 or PLACEHOLDER_RE.search(body_text)):
                return JSONResponse(status_code=400, content={"error": {"code": "bad_story_event", "message": "60자 안에서 빈칸 없이 적어 주세요."}})
            event[key] = body_text or None
        saved["story_event"] = event
    if body.hours is not None:
        days = [None if d.closed else {"open": d.open, "close": d.close} for d in body.hours.days]
        try:
            store = hours.apply_week(store, days)
        except ValueError as error:
            return JSONResponse(status_code=400, content={"error": {"code": "bad_hours", "message": str(error)}})
        repo.put("store", body.store_id, body.store_id, store)
    repo.save_settings(body.store_id, saved)
    if body.hours is not None or body.briefing_notify is not None:
        queue.reschedule_prepare(body.store_id)
    return settings_view(body.store_id)
