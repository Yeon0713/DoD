"""GET /api/naver/place 응답 모양. 앱의 mobile/src/lib/api.ts NaverPlace 와 칸 이름이 같다."""

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

