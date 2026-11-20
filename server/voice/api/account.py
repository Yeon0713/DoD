"""가입, 로그인, 탈퇴 (v0.2.1 사장님 앱이 이전 앱의 가입 흐름을 그대로 쓰게).

이전 앱(mobile/)은 메인 서버(server/app, 8000)의 모듈로 가입했다. 그 모듈을 이 서버에 그대로 붙여서
사장님 앱은 음성 백엔드 하나(8100)만 부른다. 코드는 메인 서버의 것을 그대로 쓴다 (고치면 두 서버가 같이 바뀐다).

  /api/auth         네이버 로그인. 앱 키가 없으면 임시 네이버 로그인 화면 (테스트 계정은 server/db/test_accounts.db,
                    데모 계정 dona_demo 는 초옹장 s005 에 이어져 있다). 테스트 계정 로그아웃·탈퇴
  /api/naver        가게 찾기 (네이버 지역 검색), 가게 정보 (/place?store_id=)
  /api/stores       가게 등록, 지도 그림, 사진, 로고, 리뷰 불러오기
  /api/owner_check  사장님 확인 (목업 국세청)

이 서버의 것:
  GET  /v1/account/config   네이버 로그인을 진짜로 하는지 (앱 키가 있는지), 시연 가게
  GET  /v1/account/owner-store?owner_key=  이 계정으로 확인까지 마친 가게 (휴대폰 로그인)
  POST /v1/account/enter    가입·로그인을 마친 가게로 들어간다. 이 서버에 그 가게가 없으면 메인 데이터
                            (가게 파일, 네이버에서 읽은 등록 기록)로 만든다: 이름, 요일별 장사 시간, 메뉴, 로고, 최근 리뷰
"""

import datetime as dt
from collections import Counter
from urllib.parse import urlparse

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.core.config import settings
from app.core.error_response import ApiError
from voice import clock, config, repo
from voice.api.errors import store_not_found
from voice.jobs import label, queue

router = APIRouter(prefix="/account")

WEEKDAY_CODES = ("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN")
PLATFORM = {"NAVER": "naver", "BAEMIN": "baemin", "COUPANG": "coupang", "YOGIYO": "yogiyo"}
RECENT_REVIEWS = dt.timedelta(days=14)  # 새로 만든 가게에 넣을 리뷰 (브리핑이 읽는 밤사이 리뷰가 이 안에 있다)


def mount(app: FastAPI) -> None:
    """메인 서버 모듈을 /api/<이름> 에 붙이고, 그 모듈이 쓰는 오류 모양({"error": {code, message}})을 맞춘다."""
    from app.modules.auth import router as auth
    from app.modules.naver import router as naver
    from app.modules.owner_check import router as owner_check
    from app.modules.stores import router as stores

    for name, module in (("auth", auth), ("naver", naver), ("owner_check", owner_check), ("stores", stores)):
        app.include_router(module.router, prefix=f"/api/{name}", tags=[name])

    @app.exception_handler(ApiError)
    async def api_error(_request: Request, error: ApiError):
        return JSONResponse(status_code=error.status_code, content={"error": {"code": error.code, "message": error.message}})

    # 네이버 로그인을 마치면 돌아갈 앱 주소: 메인 서버는 자기 CORS 목록의 앱(8082, 3000)만 받는다.
    # 이 서버에서는 사장님 앱(8090)도 받는다. 메인 서버의 CORS 목록은 건드리지 않는다.
    def allowed_back(back: str) -> bool:
        parsed = urlparse(back)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        return origin in config.APP_ORIGINS or settings.allows_origin(origin)

    auth._allowed_back = allowed_back


@router.get("/config")
def account_config():
    return {"naver_real": bool(settings.naver_login_client_id and settings.naver_login_client_secret), "demo_store_id": config.DEMO_STORE_ID}


@router.get("/owner-store")
def owner_store(owner_key: str):
    """이 계정(휴대폰 번호 등)으로 사장님 확인까지 마친 가게. 휴대폰으로 다시 로그인할 때 쓴다 (네이버는 로그인 결과에 온다)."""
    from app.data_pipeline import read_store_db, registered_stores

    store_id = registered_stores.store_for_owner(owner_key)
    if not store_id or store_id not in read_store_db.list_store_ids():
        return {"store_id": None, "store_name": None}
    return {"store_id": store_id, "store_name": read_store_db.read_store(store_id)["name"]}


class EnterIn(BaseModel):
    store_id: str


@router.post("/enter")
def enter(body: EnterIn):
    store = ensure(body.store_id)
    if store is None:
        return store_not_found()
    return {"store_id": store["id"], "name": store["name"], "logo_url": store.get("logo_url")}


def _usual(days: list[dict | None]) -> tuple[str, str]:
    opened = [(d["open"], d["close"]) for d in days if d]
    return Counter(opened).most_common(1)[0][0] if opened else ("10:00", "21:00")


def ensure(store_id: str) -> dict | None:
    """이 서버에 가게가 없으면 메인 데이터로 만든다. 메인 데이터에도 없으면 None.
    초옹장(s005)처럼 fixtures 로 넣어 둔 가게는 그대로 쓴다."""
    store = repo.store(store_id)
    if store is not None:
        return store
    from app.data_pipeline import read_store_db
    from app.modules.naver.data_provider import get_place

    if store_id not in read_store_db.list_store_ids():
        return None
    place = get_place(store_id).place
    raw = read_store_db.read_store(store_id)
    days = []
    for code in WEEKDAY_CODES:
        hours = place.weekly_hours.get(code)
        days.append({"open": hours.open, "close": hours.close} if hours else None)
    if not any(days):  # 네이버에 장사 시간이 없으면 가게 파일의 것
        days = [None if i in (raw.get("closed_weekdays") or []) else {"open": raw["open_time"].strftime("%H:%M"), "close": raw["close_time"].strftime("%H:%M")}
                for i in range(7)]
    open_time, close_time = _usual(days)
    store = {
        "id": store_id, "name": place.name, "category": place.category, "address": place.address,
        "open_time": open_time, "close_time": close_time, "closed_weekdays": [i for i, d in enumerate(days) if not d],
        "naver_hours": days,  # 요일마다 다를 수 있다 (voice/hours.py 가 그날 시간을 여기서 읽는다)
        "location": {"lat": raw["lat"], "lng": raw["lng"]}, "timezone": "Asia/Seoul",
        "logo_url": place.logo,
        "menus": [{"id": f"m_{i + 1}", "name": m.name, "price": None, "photo_url": m.photo} for i, m in enumerate(place.menus)],
        "rain_menu": None, "strengths": [],
    }
    repo.put("store", store_id, store_id, store)
    if not repo.get("settings", store_id):
        repo.save_settings(store_id, {})
    now = clock.now()
    for r in read_store_db.read_reviews(store_id, now):
        if r["written_at"] < now - RECENT_REVIEWS:
            continue
        repo.save_review(label.label({
            "id": f"rv_{r['review_id']}", "store_id": store_id, "platform": PLATFORM.get(r.get("platform") or "", "naver"),
            "rating": r["rating"], "order_channel": r.get("order_channel") or "hall", "written_at": clock.iso(r["written_at"]),
            "text": r["content"], "reply_status": "none",
        }))
    queue.schedule_prepare(store_id)
    return store
