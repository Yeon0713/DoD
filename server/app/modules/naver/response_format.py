"""GET /api/naver/place 응답 모양. 앱의 mobile/src/lib/api.ts NaverPlace 와 칸 이름이 같다."""

from typing import Literal

from pydantic import BaseModel

from app.planner.data_shapes import Daypart, Weekday


class OpenClose(BaseModel):
    open: str  # "10:00"
    close: str  # "22:00". 자정을 넘기면 "03:00" 처럼 오픈보다 이르다


class StartEnd(BaseModel):
    start: str
    end: str


class PlaceMenu(BaseModel):
    name: str
    photo: str | None  # 메뉴 사진 주소. DB 에 사진이 없어서 지금은 None


class PlaceNews(BaseModel):
    """네이버 플레이스 소식 카드 (사장님이 올린 알림·이벤트)"""

    news_id: str
    title: str
    body: str
    category: str  # "알림", "EVENT" 같은 네이버 분류
    period: str | None = None  # 적힌 기간. 예) "2026.10.01. ~ 2026.10.09."
    created: str | None = None  # 올린 날 "2026-10-01"
    photos: list[str] = []


class NaverPlace(BaseModel):
    place_id: str
    name: str
    address: str  # 도로명 주소 (사장님이 검색해서 고른 가게가 있으면 그 주소)
    category: str  # 업종. 예) "돈가스"
    weekly_hours: dict[Weekday, OpenClose | None]  # 요일별 장사 시간. None 이면 쉬는 날
    break_time: StartEnd | None  # 브레이크 타임. DB 에 칸이 없어서 지금은 None
    dayparts: dict[Daypart, StartEnd]  # 알림을 보낼지 정할 때 쓰는 장사 시간대
    busy_dayparts: list[Daypart]
    menus: list[PlaceMenu]
    photo_count: int
    review_count: int
    rating: float  # 평균 별점 (소수 첫째 자리)
    # 포스터에 쓰는 가게 사진과 로고 (사장님이 네이버 플레이스에 올린 매장 사진, 대표 사진. 손님 사진은 넣지 않는다)
    store_photos: list[str] = []
    profile_photo: str | None = None
    # 로고 (바탕을 지운 PNG, 서버 주소 /api/stores/.../logo): 사장님이 앱에서 올린 로고 → 네이버 소식에서 찾은 로고 → 없으면 None
    # 로고가 없어도 포스터에는 가게 이름·주소가 글자로 들어간다
    logo: str | None = None
    logo_source: Literal["OWNER", "NAVER"] | None = None
    facilities: list[str] = []  # 편의 시설. 예) "단체 이용 가능", "예약"
    news: list[PlaceNews] = []  # 네이버 소식 카드 (최근 것이 앞)


class NaverPlaceResponse(BaseModel):
    is_example: bool
    place: NaverPlace


class SearchedPlace(BaseModel):
    """네이버 지역 검색에서 찾은 가게 하나 (상호, 업종, 주소, 좌표만 온다. 메뉴, 영업시간, 리뷰는 오지 않는다)."""

    name: str
    category: str  # 예) "돈가스" (네이버 "음식점>일식>돈가스" 의 마지막 칸)
    address: str  # 도로명 주소. 없으면 지번 주소
    jibun_address: str
    lat: float
    lng: float


class PlaceSearchResponse(BaseModel):
    items: list[SearchedPlace]

