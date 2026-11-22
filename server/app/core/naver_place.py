"""네이버 지도 가게 정보 가져오기 (크롤링).

네이버는 가게의 영업시간, 메뉴를 주는 공개 API 가 없어서 네이버 지도 모바일 가게 화면(m.place.naver.com)에 담긴
데이터(__APOLLO_STATE__)를 읽는다. 매장 등록 때 한 번, 사장님이 "다시 불러오기"를 누를 때만 부른다.
읽은 값은 DB 에 저장해 두고 평소에는 DB 를 쓴다 (app/modules/stores).

- find_place_id: 가게 이름과 좌표로 네이버 지도 가게 id 를 찾는다 (네이버 모바일 검색 화면에서)
- crawl_place: 가게 id 로 이름, 업종, 주소, 좌표, 요일별 영업시간, 브레이크 타임, 메뉴(이름, 가격, 사진)를 읽는다
  소식 탭(사장님이 올린 알림·이벤트 카드)도 읽고, 소식 사진 중 로고처럼 생긴 것이 있으면 로고로 쓴다 (app/core/logo_image.py)

네이버 화면 구조가 바뀌면 깨질 수 있다. 그때는 PlaceCrawlError 를 내고, 앱은 사장님이 직접 적게 안내한다.
"""

import json
import math
import re
from dataclasses import dataclass, field
from urllib.parse import urlparse

import httpx

UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)
SEARCH_URL = "https://m.search.naver.com/search.naver"
PLACE_URL = "https://m.place.naver.com/place/{place_id}/home"
FEED_URL = "https://m.place.naver.com/place/{place_id}/feed"
IMAGE_HOSTS = ("pstatic.net",)  # 네이버 사진이 있는 곳. 로고를 찾으려고 받는 사진은 이 주소만
MAX_LOGO_TRIES = 10  # 로고를 찾으려고 받아 보는 소식 사진 수
DAY_CODES = {"월": "MON", "화": "TUE", "수": "WED", "목": "THU", "금": "FRI", "토": "SAT", "일": "SUN"}


class PlaceCrawlError(Exception):
    """네이버 지도에서 가게 정보를 읽지 못했다."""


@dataclass
class PlaceMenu:
    name: str
    price: int | None  # 원. "변동" 처럼 숫자가 아니면 None
    photo: str | None


@dataclass
class PlaceNews:
    """네이버 플레이스 소식 카드 하나 (사장님이 올린 알림, 이벤트)"""

    news_id: str
    title: str
    body: str
    category: str  # "알림", "EVENT" 같은 네이버 분류
    period: str | None  # "2026.10.01. ~ 2026.10.09." 처럼 적힌 기간. 없으면 None
    created: str | None  # 올린 날 "2026-10-01"
    photos: list[str] = field(default_factory=list)


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
    # 사장님이 네이버 플레이스에 올린 매장 사진 (포스터에 쓴다). 대표 사진이 맨 앞. 손님이 올린 사진은 넣지 않는다
    photos: list[str] = field(default_factory=list)
    profile_photo: str | None = None  # 대표 사진 (네이버 지도에서 가게를 열면 맨 위에 보이는 사진)
    # 로고 사진 주소. 네이버 플레이스에는 로고 칸이 없어서, 소식 사진 중 로고처럼 생긴 것(흰 바탕에 그림 하나)을 찾아 둔다. 없으면 None
    logo: str | None = None
    facilities: list[str] = field(default_factory=list)  # 편의 시설. 예) "단체 이용 가능", "예약", "포장"
    news: list[PlaceNews] = field(default_factory=list)  # 소식 탭 카드 (최근 것이 앞)

    def to_dict(self) -> dict:
        return {**self.__dict__, "menus": [m.__dict__ for m in self.menus], "news": [n.__dict__ for n in self.news]}

    @staticmethod
    def from_dict(d: dict) -> "PlaceInfo":
        # 예전에 "24:00" 그대로 저장해 둔 정보도 읽을 때 맞춘다
        weekly = {code: h and {**h, "close": _midnight_close(h["close"])} for code, h in d["weekly_hours"].items()}
        menus, news = [PlaceMenu(**m) for m in d.get("menus", [])], [PlaceNews(**n) for n in d.get("news", [])]
        return PlaceInfo(**{**d, "weekly_hours": weekly, "menus": menus, "news": news})


def _midnight_close(end: str) -> str:
    """자정 마감 "24:00" 은 "23:59" 로 맞춘다 (가게 시간 규칙은 00:00~23:59). "00:00" 은 그대로 둔다 (자정을 넘기는 가게로 본다)."""
    return "23:59" if end == "24:00" else end


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


_WEEK = list(DAY_CODES)  # 월 ~ 일
_GROUPS = {"매일": _WEEK, "평일": _WEEK[:5], "주말": _WEEK[5:]}


def day_codes(label: str) -> list[str]:
    """네이버 영업시간 줄의 요일 이름 → 요일 코드. "월", "매일", "평일", "주말", "월~금", "월, 수, 금" 을 읽는다. 모르면 빈 목록 (공휴일 등)."""
    label = label.strip()
    if label in _GROUPS:
        return [DAY_CODES[d] for d in _GROUPS[label]]
    span = re.fullmatch(r"([월화수목금토일])\s*[~\-–]\s*([월화수목금토일])", label)
    if span:
        start, end = _WEEK.index(span.group(1)), _WEEK.index(span.group(2))
        days = _WEEK[start : end + 1] if start <= end else _WEEK[start:] + _WEEK[: end + 1]
        return [DAY_CODES[d] for d in days]
    parts = [p.strip() for p in re.split(r"[,\s]+", label) if p.strip()]
    if parts and all(p in DAY_CODES for p in parts):
        return [DAY_CODES[p] for p in parts]
    return []


def _price(text: str | None) -> int | None:
    digits = re.sub(r"[^\d]", "", text or "")
    return int(digits) if digits else None


def _state(html: str) -> dict:
    match = re.search(r"window\.__APOLLO_STATE__\s*=\s*(\{.*?\});\s*window\.", html, re.S)
    if not match:
        raise PlaceCrawlError("네이버 지도 화면 모양이 바뀌었어요")
    return json.loads(match.group(1))


def parse_place(place_id: str, html: str) -> PlaceInfo:
    """가게 화면 html 에서 정보를 읽는다 (테스트에서 저장해 둔 html 로도 부른다)."""
    state = _state(html)
    base = state.get(f"PlaceDetailBase:{place_id}")
    if not base:
        raise PlaceCrawlError("네이버 지도에 이 가게 정보가 없어요")
    detail = next((v for k, v in state.get("ROOT_QUERY", {}).items() if k.startswith("placeDetail(")), {})

    weekly: dict[str, dict | None] = {code: None for code in DAY_CODES.values()}
    breaks: list[tuple[str, str]] = []
    closed_note = None
    rows: list[tuple[list[str], dict]] = []
    for group in detail.get("newBusinessHours") or []:
        closed_note = closed_note or group.get("comingRegularClosedDays") or group.get("freeText") or None
        for day in group.get("businessHours") or []:
            codes = day_codes(day.get("day", ""))
            if codes and day.get("businessHours"):
                rows.append((codes, day))  # 공휴일 같은 줄은 요일이 없어 건너뛴다
    # "매일"·"평일" 같은 묶음 줄을 먼저 채우고, "토"처럼 하루만 적은 줄로 덮는다
    for codes, day in sorted(rows, key=lambda r: -len(r[0])):
        hours = day["businessHours"]
        for code in codes:
            weekly[code] = {"open": hours["start"], "close": _midnight_close(hours["end"])}
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

    photos, profile_photo = _store_photos(state, detail)
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
        photos=photos,
        profile_photo=profile_photo,
        logo=_logo(base, detail),
        facilities=[c for c in (base.get("conveniences") or []) if isinstance(c, str)],
    )


def _store_photos(state: dict, detail: dict) -> tuple[list[str], str | None]:
    """(사장님이 올린 매장 사진들, 대표 사진). 대표 사진은 detail.images, 매장 사진은 위쪽 사진 줄의 business 사진."""
    representative = [img.get("origin") for img in ((detail.get("images") or {}).get("images") or []) if img.get("origin")]
    business = [
        item.get("originalUrl")
        for key, item in state.items()
        if key.startswith("PlaceDetailTopPhotoItem:") and item.get("mediaSource") == "business" and item.get("mediaFormat") == "image" and item.get("originalUrl")
    ]
    photos = list(dict.fromkeys(representative + business))  # 겹치는 사진은 한 번만, 대표 사진이 앞
    return photos, (representative[0] if representative else photos[0] if photos else None)


def _logo(base: dict, detail: dict) -> str | None:
    """네이버 플레이스에 로고처럼 보이는 칸이 있으면 그 주소. 지금 화면에는 로고 칸이 없다 (나중에 생기면 여기서 읽는다)."""
    for source in (base, detail):
        for key, value in source.items():
            if "logo" in key.lower() and isinstance(value, str) and value.startswith("http"):
                return value
    return None


def parse_news(html: str) -> list[PlaceNews]:
    """소식 탭 html 에서 소식 카드를 읽는다 (화면에 실린 순서 = 최근 것이 앞)."""
    state = _state(html)
    feeds = next((v for k, v in state.get("ROOT_QUERY", {}).items() if k.startswith("feeds(")), None)
    keys = [ref.get("__ref") for ref in (feeds or {}).get("feeds") or []] if feeds else [k for k in state if k.startswith("Feed:")]
    news = []
    for key in keys:
        item = state.get(key) or {}
        if item.get("__typename") != "Feed" or item.get("isDeleted"):
            continue
        created = str(item.get("createdString") or "")
        news.append(PlaceNews(
            news_id=str(item.get("feedId") or item.get("id") or key),
            title=(item.get("title") or "").strip(),
            body=(item.get("desc") or "").strip(),
            category=item.get("category") or "",
            period=item.get("period") or None,
            created=f"{created[:4]}-{created[4:6]}-{created[6:8]}" if re.fullmatch(r"\d{8}", created) else None,
            photos=[m["thumbnail"] for m in item.get("media") or [] if m.get("mediaType") == "IMAGE" and m.get("thumbnail")],
        ))
    return news


def _image(url: str) -> bytes | None:
    host = urlparse(url).hostname or ""
    if not url.startswith("https://") or not any(host == h or host.endswith("." + h) for h in IMAGE_HOSTS):
        return None
    try:
        res = httpx.get(url, headers={"User-Agent": UA, "Referer": "https://m.place.naver.com/"}, timeout=10)
    except httpx.HTTPError:
        return None
    return res.content if res.status_code == 200 and res.headers.get("content-type", "").startswith("image/") else None


def find_logo(news: list[PlaceNews]) -> str | None:
    """소식 사진 중 로고처럼 생긴 사진 (가장 로고다운 것). 없으면 None"""
    from app.core import logo_image  # Pillow 는 로고를 찾을 때만 불러온다

    best: tuple[float, str] | None = None
    for url in list(dict.fromkeys(p for n in news for p in n.photos))[:MAX_LOGO_TRIES]:
        raw = _image(url)
        score = logo_image.logo_score(raw) if raw else None
        if score is not None and (best is None or score > best[0]):
            best = (score, url)
    return best[1] if best else None


def crawl_place(place_id: str) -> PlaceInfo:
    if not re.fullmatch(r"\d{5,}", place_id):
        raise PlaceCrawlError("가게 id 가 이상해요")
    info = parse_place(place_id, _get(PLACE_URL.format(place_id=place_id)))
    # 소식은 없어도 가게 정보는 그대로 쓴다 (소식 탭을 못 읽으면 빈 목록)
    try:
        info.news = parse_news(_get(FEED_URL.format(place_id=place_id)))
    except (PlaceCrawlError, ValueError):
        info.news = []
    if not info.logo:
        info.logo = find_logo(info.news)
    return info
