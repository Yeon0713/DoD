"""GET /v1/home: 앱을 켰을 때. 도나가 무엇을 준비해 뒀는지 (말하지 않는다, say 없음)."""

from fastapi import APIRouter

from voice import clock, repo, speech
from voice.api.errors import store_not_found
from voice.jobs import briefing

router = APIRouter()


@router.get("/home")
def home(store_id: str):
    store = repo.store(store_id)
    if store is None:
        return store_not_found()
    now = clock.now()
    brief = briefing.current(store_id)
    body = {
        "store": {"id": store_id, "name": store["name"]},
        "date": now.date().isoformat(),
        "date_label": f"{now.month}월 {now.day}일 {speech.weekday(now.date())}요일",
        "briefing_ready": brief is not None,
        "prepared_at": brief["prepared_at"] if brief else None,
    }
    if brief is None:  # 준비 전 홈 (14장 6번 제안)
        return {**body, "headline": "아직 준비하고 있어요", "cards": [], "suggestions": []}
    return {**body, "headline": "오늘 일정 브리핑 준비했어요",
            "cards": [{"type": "rows", "id": "prepared", "rows": brief["home_rows"]}], "suggestions": ["오늘 일정 브리핑해 줘"]}
