"""개발·시연용 API (문서 9장). 실제 리뷰 플랫폼·예약 시스템 대신 여기로 데이터를 넣고 시각을 움직인다.

2026-11-18: 영업 중에 들어온 아쉬운 리뷰는 사장님 앱에 알린다 (jobs/review_loop.py). 문 닫은 뒤의 리뷰는 지금처럼
백엔드만 알고 있다가(허락받았으면 바로 답하기) 브리핑 때 말한다.
GET /dev/platform 은 시연 화면 오른쪽 '리뷰 플랫폼' 칸이다 (올라간 답글이 보인다. 실제 플랫폼 화면을 흉내 내지 않는다).
"""

import datetime as dt
import json

from fastapi import APIRouter, Body
from fastapi.responses import JSONResponse

from voice import clock, config, hr, repo, speech, staff, staff_db
from voice.api.errors import store_not_found
from voice.api.schemas import ClockIn, DemoReviewIn, ReviewIn, RunIn
from voice import prepared_snapshot, staff_orders
from voice.api.schemas import ClockIn, DemoReviewIn, ReviewIn, RunIn, StoryEventIn
from voice.jobs import auto_reply, briefing, label, queue, review_loop

router = APIRouter(prefix="/dev")


def load_fixtures(payload: dict) -> dict:
    """가게, 예약, 행사, 경기, 날씨, 리뷰를 한꺼번에 넣는다. 그 가게의 이전 데이터와 대화 기록은 지운다."""
    store = payload["store"]
    store_id = store["id"]
    repo.delete_store(store_id)
    staff_orders.forget_recent()
    repo.put("store", store_id, store_id, {**store, "fixture": True})  # 시연 가게 표시 (시계를 멈춘 동안 이 가게 작업만 돈다, jobs/queue.py)
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
    hr.set_ranks(store_id, payload.get("hr") or {})  # 업무별 출발 직급 (없는 업무는 인턴, voice/hr.py)
    hr.seed_history(store_id, payload.get("hr_history") or [])  # 지난 반응 기록 (시연 가게)
    _put_pos_data(store_id, payload)
    for item in payload.get("activity", []):  # 지난 날 한 일 (일정 탭)
        repo.put("activity", f"{store_id}:{item['at'][:10]}:{item['id']}", store_id, item)
    staff.seed(store_id, payload)  # 알바생, 초대 코드, 매뉴얼 (알바생 할 일)
    for name, item in payload.get("demo_reviews", {}).items():  # 시연 리뷰 (POST /v1/dev/demo_review)
        repo.put("demo_review", f"{store_id}:{name}", store_id, {**item, "name": name})
    queue.schedule_prepare(store_id)
    return {"store_id": store_id, "reviews": len(payload.get("reviews", []))}


def _put_pos_data(store_id: str, payload: dict) -> None:
    """포스 매출(매출 탭)과 다시 온 손님. 목업 단계라 fixtures 가 곧 포스·리뷰를 이어 본 결과다.
    사장님이 정한 것이 아니라서, 켤 때마다 fixtures 의 것으로 새로 넣어도 된다 (seed)."""
    if "sales" in payload:
        repo.put("sales", store_id, store_id, payload["sales"])
    for item in payload.get("revisits", []):
        repo.put("revisit", f"{store_id}:{item['id']}", store_id, item)


def add_review(body: dict) -> dict:
    store_id = body["store_id"]
    review_id = f"rv_{store_id}_{1000 + repo.next_number(f'review:{store_id}')}"  # repo 키는 가게를 가리지 않는다
    written_at = body.get("written_at") or clock.iso(clock.now())
    review = repo.save_review(label.label({**body, "written_at": written_at, "id": review_id, "reply_status": "none"}))
    review_loop.on_new_review(review)  # 영업 중이면 알림 고리, 문 닫은 뒤면 10분 뒤 바로 답하기
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


def _mark_fixture(store_id: str) -> None:
    """fixtures 로 넣은 가게 표시. 저장본으로 되살렸거나 표시 전에 넣어 둔 가게에도 붙인다."""
    store = repo.store(store_id)
    if store is not None and not store.get("fixture"):
        repo.put("store", store_id, store_id, {**store, "fixture": True})


def seed(name: str, *, fresh: bool) -> dict:
    """시연 가게 하나를 시연할 수 있는 상태로: 시계를 그 파일의 demo.now 로 맞추고, (fresh 거나 가게가 없으면) 데이터를 넣고,
    브리핑을 바로 준비한다 (문 열기 한 시간 전보다 일찍이어도). 답글을 에이전트가 쓰느라 1 ~ 2분 걸릴 수 있다."""
    payload = fixture(name)
    if payload.get("demo", {}).get("now"):
        clock.set_now(clock.parse(payload["demo"]["now"]))
    store_id = payload["store"]["id"]
    result = {"store_id": store_id, "loaded": False}
    if (fresh or repo.store(store_id) is None) and prepared_snapshot.restore(name, payload):
        # 밤사이 준비 결과 저장본 (voice/prepared_snapshot.py): CLOVA 를 기다리지 않고 바로 브리핑할 수 있다
        _mark_fixture(store_id)
        queue.run_due()
        briefing.assemble(store_id)  # 브리핑 단계는 지금 코드로 다시 짠다 (순서·문구를 고쳐도 저장본을 다시 만들지 않게, 모델 안 부름)
        return {"store_id": store_id, "loaded": True, "prepared": "snapshot", "now": clock.iso(clock.now())}
    if fresh or repo.store(store_id) is None:
        result = {**load_fixtures(payload), "loaded": True}
    else:  # 가게가 이미 있으면 사장님 기록은 두고, 매출과 다시 온 손님만 fixtures 의 새 것으로
        _put_pos_data(store_id, payload)
        if not staff_db.members(store_id):  # 알바생 표가 생기기 전의 voice.db: 알바생과 매뉴얼만 넣는다
            staff.seed(store_id, payload)
    _mark_fixture(store_id)
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


@router.post("/demo_review")
def post_demo_review(body: DemoReviewIn):
    """픽스처의 시연 리뷰(leak, missing, cold, hall)를 지금 시각에 넣는다 (시연 화면의 '리뷰 넣기')."""
    if repo.store(body.store_id) is None:
        return store_not_found()
    item = repo.get("demo_review", f"{body.store_id}:{body.name}")
    if item is None:
        return JSONResponse(status_code=404, content={"error": {"code": "demo_review_not_found", "message": f"시연 리뷰 '{body.name}'가 없어요."}})
    fields = {k: item[k] for k in ("platform", "rating", "text", "order_channel", "menus") if k in item}
    review = add_review({**fields, "store_id": body.store_id, "written_at": body.written_at})
    return {"review_id": review["id"], "alert": repo.get("alert", f"al_{review['id']}") is not None}


PLATFORM_LABELS = {"baemin": "배달 앱 리뷰", "coupang": "배달 앱 리뷰", "yogiyo": "배달 앱 리뷰", "naver": "지도 리뷰"}


def _when_label(moment, now) -> str:
    return speech.clock_label(moment) if moment.date() == now.date() else f"{moment.month}월 {moment.day}일"


@router.get("/platform")
def get_platform(store_id: str, limit: int = 8):
    """시연 화면 오른쪽 위: 손님 리뷰와 올라간 답글 (최근 것 먼저). 답글은 올린 것만 보인다."""
    if repo.store(store_id) is None:
        return store_not_found()
    now = clock.now()
    written = [r for r in repo.reviews(store_id) if clock.parse(r["written_at"]) <= now]
    items = []
    for r in sorted(written, key=lambda r: r["written_at"], reverse=True)[:limit]:
        posted = r.get("reply_status") == "posted" and r.get("reply_posted_at") and clock.parse(r["reply_posted_at"]) <= now
        reply = None
        if posted:
            at = clock.parse(r["reply_posted_at"])
            reply = {"text": r["reply_text"], "posted_label": _when_label(at, now), "fresh": now - at <= dt.timedelta(minutes=2)}
        items.append({"id": r["id"], "platform_label": PLATFORM_LABELS.get(r.get("platform"), "리뷰"), "rating": r["rating"],
                      "text": r["text"], "menus": r.get("menus") or [], "written_label": _when_label(clock.parse(r["written_at"]), now),
                      "reply": reply})
    return {"now": clock.iso(now), "now_label": speech.clock_label(now), "items": items}


@router.get("/messenger")
def get_messenger(store_id: str, to: str | None = None):
    """시연 화면의 알바생 휴대폰에 띄우는 '사장님이 보낸 글' (Figma F-01, 카카오톡 모양 예시 화면).
    사장님이 "카카오톡으로 보내 줘"라고 한 초대 글만 보인다. to 를 주면 그 사람에게 간 것만 (예: to=하린).
    link 를 누르면 알바생 입장 화면(/staff)에 코드가 채워진다. 실제 카카오톡을 대신하는 개발용 화면이다."""
    store = repo.store(store_id)
    if store is None:
        return store_not_found()
    now = clock.now()
    person = staff.find_by_name(store_id, to) if to else None
    items = []
    for invite in reversed(staff_db.store_invites(store_id)):  # 오래된 것부터 (대화처럼)
        if not invite["shared_at"] or clock.parse(invite["shared_at"]) > now or (person and invite["staff_id"] != person["id"]):
            continue
        at = clock.parse(invite["shared_at"])
        items.append({
            "id": invite["code"], "text": f"{store['name']} 알바생 할 일 페이지예요. 아래 주소로 들어와서 초대 코드를 넣어 주세요.",
            "url": staff_orders.invite_url(store), "code": f"{invite['code'][:3]} {invite['code'][3:]}",
            "link": f"/staff?code={invite['code']}", "time_label": speech.clock_label(at),
            "date_label": f"{at.month}월 {at.day}일 {speech.weekday(at.date())}요일", "usable": not invite["revoked_at"],
        })
    return {"from": "사장님", "to": person["call"] if person else to, "store": {"name": store["name"], "logo_url": store.get("logo_url")},
            "items": items}


@router.post("/staff_join")
def post_staff_join(body: dict = Body(...)):
    """연습용: 초대·가입을 건너뛰고 알바생을 가입한 상태로 만들어 로그인 표시를 준다 (개발자 모드 '하린 바로 가입')."""
    store_id = body.get("store_id", "")
    if repo.store(store_id) is None:
        return store_not_found()
    person = staff.ensure_person(store_id, body.get("name") or "하린")
    if not person["joined"]:
        now = clock.iso(clock.now())
        staff_db.update_member(person["id"], status="joined", signed_up_at=now, started_at=now)
    return {"token": staff.issue_token(person["id"]), "staff_id": person["id"], "name": person["call"]}


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
    if body.job == "instagram_publish":  # 걸어 둔 인스타 게시 작업 중 시각이 된 것을 돌린다
        return {"job": body.job, "ran": [job for job in queue.run_due() if ":instagram_publish:" in job]}
    prepared = briefing.prepare(store_id)
    return {"job": body.job, "prepared_at": prepared["prepared_at"], "sources": prepared["sources"]}


@router.post("/story_event")
def post_story_event(body: StoryEventIn):
    """비 오는 날 스토리 이벤트 포스터를 브리핑 없이 바로 그리기 시작한다 (/dev 시연용). 다 그리면 알림(story_event)이 간다."""
    from voice.instagram import story_event

    if repo.store(body.store_id) is None:
        return store_not_found()
    record = story_event.start(body.store_id)
    if record is None:
        return JSONResponse(status_code=409, content={"error": {"code": "no_story_event", "message": "설정에 스토리 이벤트(혜택, 알바생 할 일)가 없어요"}})
    return story_event.get(record["id"])


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


@router.post("/hr")
def post_hr(payload: dict = Body(...)):
    """직급을 바꾼다 (시연·시험): {"store_id": "s005", "ranks": {"negative_reply": "assistant"}}. 바뀐 직급은 다음 준비부터 보인다."""
    store_id = payload["store_id"]
    if repo.store(store_id) is None:
        return store_not_found()
    hr.set_ranks(store_id, payload.get("ranks") or {})
    return {"store_id": store_id, "ranks": {job: hr.rank(store_id, job) for job, spec in hr.JOBS.items() if not spec.get("future")}}


@router.get("/audit")
def get_audit(store_id: str, day: str | None = None):
    """감사 기록과 업무별 요약 (개발자 대시보드 감사 탭, 감사팀 계획 12장). day 를 비우면 오늘 (시연 시계)."""
    from voice.audit import log as audit_log

    if repo.store(store_id) is None:
        return store_not_found()
    return audit_log.day_summary(store_id, dt.date.fromisoformat(day) if day else clock.now().date())
