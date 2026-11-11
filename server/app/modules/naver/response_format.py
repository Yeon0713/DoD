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
