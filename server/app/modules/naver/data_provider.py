"""'네이버 플레이스에서 가게 정보 불러오기'를 DB 가게 정보로 대신한다. DB(지호) → 서버 → 앱.

네이버 플레이스 정보를 가져오는 공개 API 가 없어서(해커톤 결정), 앱의 처음 쓰는 날 화면(06-2c)이
같은 모양으로 동작하도록 DB 의 가게 이름, 장사 시간, 쉬는 날, 메뉴, 리뷰 수와 평균 별점을 돌려준다.
"""

from app.core.seoul_time import now_seoul
from app.data_pipeline import read_store_db
from app.data_pipeline.analysis_to_plan_inputs import DEFAULT_BUSY_DAYPARTS, default_notice_dayparts, hhmm
from app.modules.naver.response_format import NaverPlace, NaverPlaceResponse, OpenClose, PlaceMenu

WEEKDAY_CODES = ("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN")


def get_place(store_id: str) -> NaverPlaceResponse:
    store = read_store_db.read_store(store_id)
    open_time, close_time = hhmm(store["open_time"]), hhmm(store["close_time"])
    closed = set(store["closed_weekdays"] or [])
    reviews = read_store_db.read_reviews(store_id, now_seoul())
    place = NaverPlace(
        place_id=f"db_{store_id}",
        name=store["name"],
        weekly_hours={
            day: None if day in closed else OpenClose(open=open_time, close=close_time) for day in WEEKDAY_CODES
        },
        break_time=None,
        dayparts=default_notice_dayparts(open_time, close_time),
        busy_dayparts=DEFAULT_BUSY_DAYPARTS,
        menus=[PlaceMenu(name=row["name"], photo=None) for row in read_store_db.read_menus(store_id)],
        photo_count=0,
        review_count=len(reviews),
        rating=round(sum(r["rating"] for r in reviews) / len(reviews), 1) if reviews else 0.0,
    )
    return NaverPlaceResponse(is_example=False, place=place)
