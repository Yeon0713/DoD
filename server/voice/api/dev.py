"""개발·시연용 API (문서 9장). 실제 리뷰 플랫폼·예약 시스템 대신 여기로 데이터를 넣고 시각을 움직인다.

리뷰가 들어와도 앱에는 아무것도 보내지 않는다. 백엔드만 알고 있다가(나누기, 허락받았으면 바로 답하기) 브리핑 때 말한다.
"""

import json

from fastapi import APIRouter, Body

from voice import clock, config, repo
from voice.api.errors import store_not_found
from voice.api.schemas import ClockIn, ReviewIn, RunIn
from voice.jobs import auto_reply, briefing, label, queue

router = APIRouter(prefix="/dev")


def load_fixtures(payload: dict) -> dict:
    """가게, 예약, 행사, 경기, 날씨, 리뷰를 한꺼번에 넣는다. 그 가게의 이전 데이터와 대화 기록은 지운다."""
    store = payload["store"]
    store_id = store["id"]
    repo.delete_store(store_id)
    repo.put("store", store_id, store_id, store)
    for item in payload.get("reservations", []):
        kind = "group" if item["party_size"] >= config.GROUP_MIN_PEOPLE else "general"
        repo.put("reservation", item["id"], store_id, {**item, "kind": kind})
    for kind in ("event", "game"):
        for item in payload.get(f"{kind}s", []):
            repo.put(kind, item["id"], store_id, item)
    for day in payload.get("weather", []):
        repo.put("weather", f"{store_id}:{day['date']}", store_id, day)
    for raw in payload.get("reviews", []):
        repo.save_review(label.label({"reply_status": "none", **raw, "store_id": store_id}))
    if "settings" in payload:
        repo.save_settings(store_id, payload["settings"])
    if "sales" in payload:  # 포스 매출 (매출 탭). 목업 단계라 fixtures 가 곧 포스에서 받은 것이다
        repo.put("sales", store_id, store_id, payload["sales"])
    for item in payload.get("activity", []):  # 지난 날 한 일 (일정 탭)
        repo.put("activity", f"{store_id}:{item['at'][:10]}:{item['id']}", store_id, item)
    queue.schedule_prepare(store_id)
    return {"store_id": store_id, "reviews": len(payload.get("reviews", []))}


def add_review(body: dict) -> dict:
    store_id = body["store_id"]
    review_id = f"rv_{1000 + repo.next_number(f'review:{store_id}')}"
    review = repo.save_review(label.label({**body, "id": review_id, "reply_status": "none"}))
    if review["sentiment"] == "negative":
        queue.add(store_id, "auto_reply", clock.parse(review["written_at"]) + config.AUTO_REPLY_DELAY, {"review_id": review_id})
    queue.run_due()
    if briefing.current(store_id) and clock.parse(review["written_at"]) <= clock.now():  # 준비한 뒤 새 리뷰 → 다시 만든다
        briefing.prepare(store_id)
    return review


def fixture(name: str) -> dict:
    """fixtures/<name>.json (예: s005_choongjang)."""
    path = config.FIXTURES / f"{name}.json"
    if not path.exists() or path.parent != config.FIXTURES:
        raise FileNotFoundError(name)
    return json.loads(path.read_text(encoding="utf-8"))


def seed(name: str, *, fresh: bool) -> dict:
    """시연 가게 하나를 시연할 수 있는 상태로: 시계를 그 파일의 demo.now 로 맞추고, (fresh 거나 가게가 없으면) 데이터를 넣고,
    브리핑을 바로 준비한다 (문 열기 한 시간 전보다 일찍이어도). 답글을 에이전트가 쓰느라 1 ~ 2분 걸릴 수 있다."""
    payload = fixture(name)
    if payload.get("demo", {}).get("now"):
        clock.set_now(clock.parse(payload["demo"]["now"]))
    store_id = payload["store"]["id"]
    result = {"store_id": store_id, "loaded": False}
    if fresh or repo.store(store_id) is None:
        result = {**load_fixtures(payload), "loaded": True}
    queue.run_due()
    if briefing.current(store_id) is None:
        briefing.prepare(store_id)
    return {**result, "now": clock.iso(clock.now())}


@router.post("/fixtures")
def post_fixtures(payload: dict = Body(...)):
    """데이터를 통째로 넣는다. {"fixture": "s005_choongjang"} 처럼 이름만 주면 그 파일로 처음부터 다시 시작한다
    (시계를 demo.now 로 맞추고 브리핑까지 준비한다)."""
    if set(payload) == {"fixture"}:
        return seed(payload["fixture"], fresh=True)
    return load_fixtures(payload)


@router.post("/reviews")
def post_review(body: ReviewIn):
    if repo.store(body.store_id) is None:
        return store_not_found()
    return {"review_id": add_review(body.model_dump())["id"]}


@router.post("/clock")
def post_clock(body: ClockIn):
    """백엔드가 아는 '지금'을 바꾼다. 앞으로 옮기면 그 사이에 했어야 할 일을 예정 시각 순서로 돌린다."""
    clock.set_now(clock.parse(body.now) if body.now else None)
    ran = queue.run_due()
    return {"now": clock.iso(clock.now()), "ran": ran}


@router.post("/run")
def post_run(body: RunIn):
    store_id = body.store_id
    if repo.store(store_id) is None:
        return store_not_found()
    if body.job == "collect":  # 목업 단계라 fixtures 와 dev/reviews 로 넣은 것이 곧 모은 것이다
        data = repo.kinds_of(store_id)
        return {"job": body.job, "collected": {kind: len(rows) for kind, rows in data.items() if kind not in ("job", "turn", "session")}}
    if body.job == "label_reviews":
        reviews = [repo.save_review(label.label(r)) for r in repo.reviews(store_id)]
        return {"job": body.job, "labeled": len(reviews)}
    if body.job == "auto_reply":
        return {"job": body.job, "replied": auto_reply.reply_pending(store_id)}
    if body.job == "post_scheduled":
        return {"job": body.job, "posted": auto_reply.post_scheduled(store_id)}
    prepared = briefing.prepare(store_id)
    return {"job": body.job, "prepared_at": prepared["prepared_at"], "sources": prepared["sources"]}


@router.post("/reset")
def post_reset():
    repo.reset()
    clock.set_now(None)
    return {"ok": True}


@router.get("/state")
def get_state(store_id: str):
    if repo.store(store_id) is None:
        return store_not_found()
    data = repo.kinds_of(store_id)
    return {"now": clock.iso(clock.now()), "settings": repo.settings(store_id), **{kind: rows for kind, rows in data.items() if kind != "settings"}}
