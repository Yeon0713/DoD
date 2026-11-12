"""네이버 지도 가게 정보 가져오기 (크롤링).

네이버는 가게의 영업시간, 메뉴를 주는 공개 API 가 없어서 네이버 지도 모바일 가게 화면(m.place.naver.com)에 담긴
데이터(__APOLLO_STATE__)를 읽는다. 매장 등록 때 한 번, 사장님이 "다시 불러오기"를 누를 때만 부른다.
읽은 값은 DB 에 저장해 두고 평소에는 DB 를 쓴다 (app/modules/stores).

- find_place_id: 가게 이름과 좌표로 네이버 지도 가게 id 를 찾는다 (네이버 모바일 검색 화면에서)
- crawl_place: 가게 id 로 이름, 업종, 주소, 좌표, 요일별 영업시간, 브레이크 타임, 메뉴(이름, 가격, 사진)를 읽는다

네이버 화면 구조가 바뀌면 깨질 수 있다. 그때는 PlaceCrawlError 를 내고, 앱은 사장님이 직접 적게 안내한다.
"""

import json
import math
import re
from dataclasses import dataclass, field

import httpx

UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)
SEARCH_URL = "https://m.search.naver.com/search.naver"
PLACE_URL = "https://m.place.naver.com/place/{place_id}/home"
DAY_CODES = {"월": "MON", "화": "TUE", "수": "WED", "목": "THU", "금": "FRI", "토": "SAT", "일": "SUN"}


class PlaceCrawlError(Exception):
    """네이버 지도에서 가게 정보를 읽지 못했다."""


@dataclass
class PlaceMenu:
    name: str
    price: int | None  # 원. "변동" 처럼 숫자가 아니면 None
    photo: str | None


@dataclass
class PlaceInfo:
    place_id: str
    name: str
    category: str
    road_address: str
    address: str
    lat: float
    lng: float
    # 요일별 영업시간. 그 요일이 없거나 쉬면 None. 예) {"MON": {"open": "11:00", "close": "20:30"}, "SAT": None}
    weekly_hours: dict[str, dict | None]
    break_time: dict | None  # 여는 날 가장 흔한 브레이크 타임. 예) {"start": "14:30", "end": "17:00"}
    menus: list[PlaceMenu] = field(default_factory=list)
    review_total: int = 0  # 네이버 방문자 리뷰 수
    closed_note: str | None = None  # "휴무일은 네이버 소식란, 인스타 참고" 같은 안내

    def to_dict(self) -> dict:
        return {**self.__dict__, "menus": [m.__dict__ for m in self.menus]}

    @staticmethod
    def from_dict(d: dict) -> "PlaceInfo":
        return PlaceInfo(**{**d, "menus": [PlaceMenu(**m) for m in d.get("menus", [])]})


def _get(url: str, params: dict | None = None) -> str:
    try:
        res = httpx.get(url, params=params, headers={"User-Agent": UA, "Referer": "https://m.map.naver.com/"}, timeout=15, follow_redirects=True)
    except httpx.HTTPError as error:
        raise PlaceCrawlError("네이버에 연결되지 않아요") from error
    if res.status_code != 200:
        raise PlaceCrawlError(f"네이버가 {res.status_code} 로 답했어요")
    return res.text


def _norm(text: str) -> str:
    return re.sub(r"[\s()·\-_.]", "", text).lower()


def _km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lng2 - lng1) / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(a))


def find_place_id(name: str, lat: float, lng: float, address: str = "") -> str:
    """이름이 같고 좌표가 가까운(0.5km 안) 네이버 지도 가게 id. 못 찾으면 PlaceCrawlError."""
    region = " ".join(address.split()[:2])  # 예) "강원특별자치도 춘천시" → 같은 이름 다른 지점을 줄인다
    html = _get(SEARCH_URL, {"query": f"{region} {name}".strip()})
    best: tuple[float, str] | None = None
    for match in re.finditer(r'"id":"(\d{5,})","name":"([^"]+)"', html):
        place_id, found_name = match.groups()
        if _norm(found_name) != _norm(name):
            continue
        near = html[match.end() : match.end() + 3000]
        x, y = re.search(r'"x":"([\d.]+)"', near), re.search(r'"y":"([\d.]+)"', near)
        distance = _km(lat, lng, float(y.group(1)), float(x.group(1))) if x and y else 0.49
        if distance <= 0.5 and (best is None or distance < best[0]):
            best = (distance, place_id)
    if best is None:
        raise PlaceCrawlError("네이버 지도에서 이 가게를 찾지 못했어요")
    return best[1]


def _price(text: str | None) -> int | None:
    digits = re.sub(r"[^\d]", "", text or "")
    return int(digits) if digits else None


def parse_place(place_id: str, html: str) -> PlaceInfo:
    """가게 화면 html 에서 정보를 읽는다 (테스트에서 저장해 둔 html 로도 부른다)."""
    match = re.search(r"window\.__APOLLO_STATE__\s*=\s*(\{.*?\});\s*window\.", html, re.S)
    if not match:
        raise PlaceCrawlError("네이버 지도 화면 모양이 바뀌었어요")
    state = json.loads(match.group(1))
    base = state.get(f"PlaceDetailBase:{place_id}")
    if not base:
        raise PlaceCrawlError("네이버 지도에 이 가게 정보가 없어요")
    detail = next((v for k, v in state.get("ROOT_QUERY", {}).items() if k.startswith("placeDetail(")), {})

    weekly: dict[str, dict | None] = {code: None for code in DAY_CODES.values()}
    breaks: list[tuple[str, str]] = []
    closed_note = None
    for group in detail.get("newBusinessHours") or []:
        closed_note = closed_note or group.get("comingRegularClosedDays") or group.get("freeText") or None
        for day in group.get("businessHours") or []:
            code = DAY_CODES.get(day.get("day", ""))
            hours = day.get("businessHours")
            if not code or not hours:
                continue  # "매일", 공휴일 같은 줄은 건너뛴다
            weekly[code] = {"open": hours["start"], "close": hours["end"]}
            for brk in day.get("breakHours") or []:
                breaks.append((brk["start"], brk["end"]))
    break_time = None
    if breaks:
        start, end = max(set(breaks), key=breaks.count)
        break_time = {"start": start, "end": end}

    menus = []
    for key, value in state.items():
        if key.startswith("PlaceMenuItem:") and value.get("name"):
            images = value.get("images") or []
            menus.append(PlaceMenu(name=value["name"], price=_price((value.get("price") or {}).get("displayText")), photo=images[0]["url"] if images else None))

    coord = base.get("coordinate") or {}
    return PlaceInfo(
        place_id=place_id,
        name=base.get("name", ""),
        category=base.get("category") or "",
        road_address=base.get("roadAddress") or base.get("address") or "",
        address=base.get("address") or "",
        lat=float(coord.get("y", 0)),
        lng=float(coord.get("x", 0)),
        weekly_hours=weekly,
        break_time=break_time,
        menus=menus,
        review_total=int(base.get("visitorReviewsTotal") or 0),
        closed_note=closed_note,
    )


def crawl_place(place_id: str) -> PlaceInfo:
    if not re.fullmatch(r"\d{5,}", place_id):
        raise PlaceCrawlError("가게 id 가 이상해요")
    return parse_place(place_id, _get(PLACE_URL.format(place_id=place_id)))
