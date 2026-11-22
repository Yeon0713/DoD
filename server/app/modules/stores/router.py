"""매장 등록과 리뷰 불러오기.

GET  /api/stores/image?url=                네이버 플레이스 사진(pstatic.net)을 대신 받아 준다 (앱이 포스터 그림에 그대로 그릴 수 있게)
GET  /api/stores/map                       지도 그림 (네이버 지도 Static Map). 검색 결과와 고른 가게 위치를 보여 준다
POST /api/stores/preview                   검색에서 고른 가게를 네이버 지도에서 읽어 "이 가게가 맞나요?"에 보여 준다 (저장 안 함)
POST /api/stores/register                  그 가게를 등록한다 (DB 에 저장). 계정과 가게는 사장님 확인(/api/owner_check)이 승인되면 잇는다
POST /api/stores/{store_id}/refresh        네이버 지도에서 가게 정보를 다시 읽어 DB 를 고친다 (사장님이 원할 때만)
GET  /api/stores/{store_id}/reviews        플랫폼별로 불러온 리뷰 수
POST /api/stores/{store_id}/reviews/import 한 플랫폼(배민, 네이버, 쿠팡이츠) 리뷰를 불러온다. 지금은 목업 리뷰를 넣는다
GET  /api/stores/{store_id}/logo           가게 로고 PNG, 바탕 지움 (올린 로고 → 네이버 소식에서 찾은 로고)
POST /api/stores/{store_id}/logo           로고 올리기 {"data_url": "data:image/png;base64,..."} (바탕을 지워 저장)
DELETE /api/stores/{store_id}/logo         올린 로고 지우기
GET  /api/stores/{store_id}/weather        기상청에서 받아 둔 그 가게 지역 날씨 (등록할 때 받고, 그 뒤 매일 자정에 새로 받는다)
POST /api/stores/{store_id}/weather/refresh 그 가게 지역 날씨를 기상청에서 다시 받는다

가게 검색은 GET /api/naver/search (네이버 지역 검색) 를 쓴다.
"""

import datetime as dt
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, BackgroundTasks, Query
from fastapi.responses import Response
from pydantic import BaseModel

from app.core import maps
from app.core.config import settings
from app.core.error_response import ApiError
from app.core.naver_place import PlaceCrawlError, PlaceInfo, crawl_place, find_place_id
from app.core.seoul_time import now_seoul
from app.data_pipeline import read_store_db, registered_stores, store_logo
from app.data_pipeline.db_rows_to_analysis_inputs import review_platform
from app.data_pipeline.read_store_db import list_store_ids
from app.data_pipeline.store_snapshot_cache import save_settings_changes
from app.modules.stores import demo_data
from app.modules.stores.review_import import PLATFORMS, make_reviews
from app.weather import auto_refresh, store_weather
from app.weather.client import KmaError

router = APIRouter()

_previews: dict[str, tuple[PlaceInfo, dt.datetime]] = {}  # 가게 id → (읽은 정보, 읽은 때). 미리 보기 뒤 등록할 때 다시 읽지 않게
PREVIEW_KEEP = dt.timedelta(minutes=30)


class PreviewRequest(BaseModel):
    name: str
    address: str = ""
    lat: float
    lng: float


class RegisterRequest(BaseModel):
    place_id: str
    # 계정과 가게는 여기서 잇지 않는다. 사장님 확인 심사(app/modules/owner_check)가 승인되면 잇는다


class ImportRequest(BaseModel):
    platform: str


def _place_payload(info: PlaceInfo) -> dict:
    return info.to_dict()


@router.get("/map-config", summary="웹 지도(JavaScript) 를 띄울 때 쓰는 Client ID")
def map_config():
    """네이버 지도 JavaScript API 는 브라우저에서 Client ID 로 불러온다 (공개해도 되는 값, NCP 콘솔에 등록한 주소에서만 동작)."""
    return {"client_id": settings.naver_maps_client_id}


IMAGE_HOSTS = ("pstatic.net",)  # 네이버 플레이스 사진이 있는 곳. 그 밖의 주소는 받지 않는다 (아무 주소나 대신 받는 통로가 되지 않게)


@router.get("/image", summary="네이버 플레이스 사진 대신 받기")
def place_image(url: str):
    parsed = urlparse(url)
    host = parsed.hostname or ""
    if parsed.scheme != "https" or not any(host == h or host.endswith("." + h) for h in IMAGE_HOSTS):
        raise ApiError(400, "BAD_IMAGE_URL", "네이버 플레이스 사진만 받을 수 있어요")
    try:
        res = httpx.get(url, headers={"Referer": "https://m.place.naver.com/"}, timeout=10, follow_redirects=True)
    except httpx.HTTPError:
        raise ApiError(502, "IMAGE_UNREACHABLE", "사진을 받지 못했어요")
    kind = res.headers.get("content-type", "")
    final = res.url.host or ""
    if not any(final == h or final.endswith("." + h) for h in IMAGE_HOSTS):  # 다른 곳으로 넘겨졌으면 받지 않는다
        raise ApiError(400, "BAD_IMAGE_URL", "네이버 플레이스 사진만 받을 수 있어요")
    if res.status_code != 200 or not kind.startswith("image/"):
        raise ApiError(502, "IMAGE_FAILED", "사진을 받지 못했어요")
    return Response(res.content, media_type=kind, headers={"Cache-Control": "public, max-age=86400"})


@router.get("/map", summary="지도 그림 (Static Map)")
def map_image(
    lat: float,
    lng: float,
    level: int = Query(16, ge=6, le=20),
    w: int = Query(640, ge=100, le=1024),
    h: int = Query(360, ge=100, le=1024),
    markers: str = Query("", description="표시할 곳. '위도,경도;위도,경도'"),
    numbered: bool = Query(False, description="핀에 1, 2, 3 번호를 붙인다 (검색 목록 번호와 같게)"),
    selected: int = Query(0, description="갈색으로 칠할 핀 번호(0부터). -1 이면 모두 갈색"),
):
    params = {"w": w, "h": h, "center": f"{lng},{lat}", "level": level, "scale": 2}
    marks = []
    for i, pair in enumerate(p for p in markers.split(";") if p.strip()):
        try:
            m_lat, m_lng = (float(v) for v in pair.split(","))
        except ValueError:
            raise ApiError(422, "INVALID_INPUT", "markers 는 '위도,경도;위도,경도' 모양이에요")
        color = "0x6f4220" if selected in (-1, i) else "0x9a9089"
        kind = f"type:n|label:{i + 1}" if numbered else "type:d"
        marks.append(f"{kind}|size:mid|color:{color}|pos:{m_lng} {m_lat}")
    # 고른 핀이 다른 핀 위에 그려지게 마지막에 둔다
    if 0 <= selected < len(marks):
        marks.append(marks.pop(selected))
    try:
        res = maps.get("/map-static/v2/raster", {**params, "markers": marks} if marks else params)
    except httpx.HTTPError:
        raise ApiError(502, "MAP_UNREACHABLE", "지도를 불러오지 못했어요")
    if res.status_code != 200:
        raise ApiError(502, "MAP_FAILED", "지도를 불러오지 못했어요")
    return Response(res.content, media_type=res.headers.get("content-type", "image/jpeg"), headers={"Cache-Control": "public, max-age=3600"})


@router.post("/preview", summary="고른 가게를 네이버 지도에서 읽기 (저장 안 함)")
def preview(body: PreviewRequest):
    try:
        place_id = find_place_id(body.name, body.lat, body.lng, body.address)
        info = crawl_place(place_id)
    except PlaceCrawlError as error:
        raise ApiError(502, "PLACE_NOT_READ", f"네이버 지도에서 가게 정보를 읽지 못했어요. {error}")
    _previews[place_id] = (info, dt.datetime.now(dt.timezone.utc))
    return {"place": _place_payload(info), "registered_store_id": registered_stores.store_for_place(place_id)}


@router.post("/register", summary="가게 등록 (DB 에 저장)")
def register(body: RegisterRequest, background: BackgroundTasks):
    cached = _previews.get(body.place_id)
    fresh = cached and dt.datetime.now(dt.timezone.utc) - cached[1] < PREVIEW_KEEP
    try:
        info = cached[0] if fresh else crawl_place(body.place_id)
    except PlaceCrawlError as error:
        raise ApiError(502, "PLACE_NOT_READ", f"네이버 지도에서 가게 정보를 읽지 못했어요. {error}")
    store_id = registered_stores.register(info)
    # 시연용: 그 가게의 영업시간과 메뉴를 따라 만든 목업 주문·매출·알바를 넣는다 (이미 있으면 그대로)
    overnight = registered_stores.is_overnight(info.weekly_hours)
    if settings.demo_store_data and not overnight:
        demo_data.fill(store_id, info.weekly_hours, info.break_time)
    # 요일별 영업시간과 브레이크 타임은 DB(등록 기록)에 있어 가게 설정의 기본이 된다 (store_snapshot_cache._registered_base).
    # 새로 등록한 가게라 지난 계산 결과는 지운다
    save_settings_changes(store_id, {})
    # 가게 좌표로 그 지역 기상청 날씨를 받는다. API 를 수십 번 불러 시간이 걸리므로 등록 응답을 보낸 뒤에 한다
    if store_weather.can_fetch(store_id):
        # 실패해도 등록은 그대로 두고(공통 목업 날씨를 쓴다) 기록만 남긴다. 그 뒤로는 매일 자정에 새로 받는다 (app/weather/auto_refresh.py)
        background.add_task(auto_refresh.refresh_store, store_id)
    return {"store_id": store_id, "place": _place_payload(info)}


def _registered(store_id: str) -> PlaceInfo:
    if store_id not in list_store_ids():
        raise ApiError(404, "STORE_NOT_FOUND", "등록한 가게가 아니에요")
    info = registered_stores.place_info(store_id)
    if info is None:
        raise ApiError(400, "NOT_REGISTERED_STORE", "목업 가게는 다시 불러올 수 없어요")
    return info


@router.post("/{store_id}/refresh", summary="네이버 지도에서 가게 정보 다시 읽기")
def refresh(store_id: str):
    info = _registered(store_id)
    try:
        info = crawl_place(info.place_id)
    except PlaceCrawlError as error:
        raise ApiError(502, "PLACE_NOT_READ", f"네이버 지도에서 가게 정보를 읽지 못했어요. {error}")
    registered_stores.refresh(store_id, info)
    return {"store_id": store_id, "place": _place_payload(info)}


@router.get("/{store_id}/reviews", summary="플랫폼별로 불러온 리뷰 수")
def review_counts(store_id: str):
    _registered(store_id)
    counts = registered_stores.imported_counts(store_id)
    return {"imported": {p: counts.get(p, 0) for p in PLATFORMS}}


def _regular_keys(store_id: str) -> list[str]:
    """목업 주문의 단골 손님 번호 (매주 c_w.., 매달 c_m..). 이번 주 좋은 리뷰 일부를 단골이 쓴 것으로 이어 단골 답글 일이 생기게 한다."""
    keys = {row["customer_key"] for row in read_store_db.read_orders(store_id, until=now_seoul()) if row["customer_key"]}
    return sorted(k for k in keys if k.startswith(("c_w", "c_m")))


@router.post("/{store_id}/reviews/import", summary="한 플랫폼 리뷰 불러오기 (지금은 목업)")
def import_reviews(store_id: str, body: ImportRequest):
    info = _registered(store_id)
    if body.platform not in PLATFORMS:
        raise ApiError(422, "INVALID_INPUT", "platform 은 BAEMIN, NAVER, COUPANG 중 하나예요")
    counts = registered_stores.imported_counts(store_id)
    if counts.get(body.platform):
        return {"platform": body.platform, "imported": counts[body.platform], "already": True}
    if registered_stores.is_mock_store(store_id):
        # 목업 가게는 리뷰가 이미 있다. 새로 만들지 않고, 있는 리뷰 중 이 플랫폼 것(배달 주문 리뷰는 배민·쿠팡이츠, 나머지는 네이버)만 표시한다
        reviews = read_store_db.read_reviews(store_id, until=now_seoul())
        ids = [r["review_id"] for r in reviews if (r.get("platform") or review_platform(r["order_channel"])) == body.platform]
        return {"platform": body.platform, "imported": registered_stores.mark_platform(store_id, body.platform, ids), "already": False}
    store = read_store_db.read_store(store_id)
    rows = make_reviews(store_id, body.platform, [m.name for m in info.menus], store["open_time"].hour, store["close_time"].hour, regulars=_regular_keys(store_id))
    added = registered_stores.add_reviews(store_id, body.platform, rows)
    # 새 리뷰로 할 일을 다시 계산하게 한다 (설정을 바꾸지 않고 계산 결과만 지운다)
    save_settings_changes(store_id, {})
    return {"platform": body.platform, "imported": added, "already": False}


class LogoUpload(BaseModel):
    data_url: str  # data:image/png;base64,...


def _known_store(store_id: str) -> None:
    if store_id not in list_store_ids():
        raise ApiError(404, "STORE_NOT_FOUND", "등록한 가게가 아니에요")


@router.get("/{store_id}/logo", summary="가게 로고")
def logo(store_id: str):
    _known_store(store_id)
    path = store_logo.path_of(store_id)
    if path is None:
        raise ApiError(404, "NO_LOGO", "가게 로고가 없어요")
    media = {"png": "image/png", "jpg": "image/jpeg", "webp": "image/webp"}[path.suffix[1:]]
    return Response(path.read_bytes(), media_type=media, headers={"Cache-Control": "public, max-age=86400"})


@router.post("/{store_id}/logo", summary="가게 로고 올리기 (바탕을 지우고 여백을 잘라 둔다)")
def upload_logo(store_id: str, body: LogoUpload):
    _known_store(store_id)
    try:
        store_logo.save(store_id, body.data_url)
    except store_logo.LogoError as error:
        raise ApiError(422, "BAD_LOGO", str(error))
    return {"logo": store_logo.url_of(store_id), "logo_source": store_logo.source_of(store_id)}


@router.delete("/{store_id}/logo", summary="올린 가게 로고 지우기 (네이버 소식에서 찾은 로고가 있으면 그것으로 돌아간다)")
def delete_logo(store_id: str):
    _known_store(store_id)
    info = registered_stores.place_info(store_id)
    removed = store_logo.remove(store_id)
    return {"removed": removed, "logo": store_logo.url_of(store_id, info.logo if info else None), "logo_source": store_logo.source_of(store_id)}


@router.get("/{store_id}/weather", summary="기상청에서 받아 둔 가게 지역 날씨")
def weather(store_id: str):
    if store_id not in list_store_ids():
        raise ApiError(404, "STORE_NOT_FOUND", "등록한 가게가 아니에요")
    return store_weather.saved_weather(store_id)


@router.post("/{store_id}/weather/refresh", summary="가게 지역 날씨를 기상청에서 다시 받기")
def refresh_weather(store_id: str):
    _registered(store_id)
    if not store_weather.can_fetch(store_id):
        raise ApiError(503, "WEATHER_KEY_MISSING", "기상청 인증키(KMA_API_KEY)가 server/.env 에 없어요")
    try:
        summary = store_weather.update_store_weather(store_id)
    except KmaError as error:
        raise ApiError(502, "WEATHER_NOT_READ", f"기상청 날씨를 받지 못했어요. {error}")
    save_settings_changes(store_id, {})
    return summary
