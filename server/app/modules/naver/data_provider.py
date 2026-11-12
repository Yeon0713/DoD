"""'네이버 플레이스에서 가게 정보 불러오기'를 DB 가게 정보로 대신한다. DB(지호) → 서버 → 앱.

네이버 플레이스 정보를 가져오는 공개 API 가 없어서(해커톤 결정), 앱의 처음 쓰는 날 화면(06-2c)이
같은 모양으로 동작하도록 DB 의 가게 이름, 장사 시간, 쉬는 날, 메뉴, 리뷰 수와 평균 별점을 돌려준다.
"""

import re

import httpx

from app.core import api_hub
from app.core.error_response import ApiError
from app.core.seoul_time import now_seoul
from app.data_pipeline import read_store_db
from app.data_pipeline import registered_stores
from app.data_pipeline.analysis_to_plan_inputs import DEFAULT_BUSY_DAYPARTS, default_notice_dayparts, hhmm
from app.modules.naver.response_format import NaverPlace, NaverPlaceResponse, OpenClose, PlaceMenu, PlaceSearchResponse, SearchedPlace, StartEnd

WEEKDAY_CODES = ("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN")


def get_place(store_id: str) -> NaverPlaceResponse:
    store = read_store_db.read_store(store_id)
    reviews = read_store_db.read_reviews(store_id, now_seoul())
    rating = round(sum(r["rating"] for r in reviews) / len(reviews), 1) if reviews else 0.0
    # 사장님이 네이버 지도에서 찾아 등록한 가게: 등록할 때 읽어 DB 에 저장해 둔 요일별 영업시간, 브레이크 타임, 메뉴를 쓴다
    info = registered_stores.place_info(store_id)
    if info is not None:
        open_days = [h for h in info.weekly_hours.values() if h]
        first = open_days[0] if open_days else {"open": hhmm(store["open_time"]), "close": hhmm(store["close_time"])}
        place = NaverPlace(
            place_id=info.place_id,
            name=info.name,
            address=info.road_address or info.address,
            category=info.category or store["category"],
            weekly_hours={day: OpenClose(**hours) if hours else None for day, hours in info.weekly_hours.items()},
            break_time=StartEnd(**info.break_time) if info.break_time else None,
            dayparts=default_notice_dayparts(first["open"], first["close"]),
            busy_dayparts=DEFAULT_BUSY_DAYPARTS,
            menus=[PlaceMenu(name=m.name, photo=m.photo) for m in info.menus],
            photo_count=sum(1 for m in info.menus if m.photo),
            review_count=len(reviews),
            rating=rating,
        )
        return NaverPlaceResponse(is_example=False, place=place)

    open_time, close_time = hhmm(store["open_time"]), hhmm(store["close_time"])
    closed = set(store["closed_weekdays"] or [])
    place = NaverPlace(
        place_id=f"db_{store_id}",
        name=store["name"],
        address=store["address"].replace("(가상)", "").strip(),
        category=store["category"],
        weekly_hours={
            day: None if day in closed else OpenClose(open=open_time, close=close_time) for day in WEEKDAY_CODES
        },
        break_time=None,
        dayparts=default_notice_dayparts(open_time, close_time),
        busy_dayparts=DEFAULT_BUSY_DAYPARTS,
        menus=[PlaceMenu(name=row["name"], photo=None) for row in read_store_db.read_menus(store_id)],
        photo_count=0,
        review_count=len(reviews),
        rating=rating,
    )
    return NaverPlaceResponse(is_example=False, place=place)


def _plain(text: str) -> str:
    """검색 결과의 <b>강조</b> 태그와 &amp; 같은 표시를 걷어 낸다."""
    text = re.sub(r"<[^>]+>", "", text)
    return text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"').replace("&#39;", "'").strip()


def search_places(query: str) -> PlaceSearchResponse:
    """네이버 지역 검색(NAVER API HUB /search/v1/local)으로 가게를 찾는다. 많아야 5곳까지 온다."""
    query = query.strip()
    if len(query) < 2:
        return PlaceSearchResponse(items=[])
    try:
        res = api_hub.get("/search/v1/local", {"query": query, "display": 5})
    except httpx.HTTPError:
        raise ApiError(502, "NAVER_UNREACHABLE", "네이버 검색에 연결되지 않아요. 잠시 뒤 다시 해 주세요")
    if res.status_code != 200:
        raise ApiError(502, "NAVER_SEARCH_FAILED", "네이버 검색이 잠시 안 돼요. 잠시 뒤 다시 해 주세요")
    items = []
    for item in res.json().get("items", []):
        try:
            # mapx, mapy 는 경도·위도에 10,000,000 을 곱한 정수 글자다
            lng, lat = int(item["mapx"]) / 1e7, int(item["mapy"]) / 1e7
        except (KeyError, ValueError):
            continue
        items.append(
            SearchedPlace(
                name=_plain(item.get("title", "")),
                category=(item.get("category") or "").split(">")[-1],
                address=item.get("roadAddress") or item.get("address", ""),
                jibun_address=item.get("address", ""),
                lat=lat,
                lng=lng,
            )
        )
    return PlaceSearchResponse(items=items)
