"""DB(지호) 읽기. 서버에서 DB 에 들어가는 문은 이 파일 하나다.

- 가게 전용 테이블(store, menu, orders, order_items, reviews, staff, shifts)은 store_id 로 그 가게 것만 읽는다.
  나중에 로그인이 생기면 '이 사장님이 이 가게를 볼 수 있는지' 검사도 여기 들어오기 전에 한 번만 하면 된다.
- 공통 테이블(events, games, weather_daily)은 모든 가게가 같이 쓴다.
  단, 사장님이 등록한 가게는 기상청에서 받은 그 지역 날씨(가게 파일 store_weather_daily)가 있으면 그것을 쓴다.
  목업 가게로 이은 실제 가게(s004 ...)는 그 날씨를 db/app_data/weather/<가게>.db 에 둔다 (registered_stores.mock_weather_engine).
- until 을 받는 함수는 그 시각까지 생긴 행만 돌려준다. 목업 DB 에는 12/31 까지 주문이 들어 있어서
  미래 데이터를 꺼내지 않도록 여기서 막는다.
- 돌려주는 값은 DB 칸 이름 그대로의 dict 목록이다. 분석이나 화면 모양으로 바꾸는 일은 다른 파일이 한다.
"""

import datetime as dt

from sqlalchemy import func, inspect, select

from db import models
from app.data_pipeline import registered_stores
from app.data_pipeline.registered_stores import review_platforms
from db.session import engine, store_db_files, store_engine


# 배달 주문과 이어진 리뷰 중 주문 번호 끝자리 0~2(약 30%)를 쿠팡이츠 리뷰로 보는 목업 가게
COUPANG_SPLIT_STORES = {"s004", "s005"}


def list_store_ids() -> list[str]:
    """DB 에 있는 가게 id 목록. 예) ["s001", "s002", "s003"]"""
    return [path.stem for path in store_db_files()]


def _store_rows(store_id: str, statement) -> list[dict]:
    with store_engine(store_id).connect() as conn:
        return [dict(row._mapping) for row in conn.execute(statement)]


def _common_rows(statement) -> list[dict]:
    with engine.connect() as conn:
        return [dict(row._mapping) for row in conn.execute(statement)]


# ── 가게 전용 ──


def read_store(store_id: str) -> dict:
    """가게 정보 한 줄. 칸: store_id, name, category, address, lat, lng, open_time, close_time, closed_weekdays, slots"""
    return _store_rows(store_id, select(models.Store.__table__))[0]


def read_menus(store_id: str) -> list[dict]:
    """칸: menu_id, name, category, price"""
    return _store_rows(store_id, select(models.Menu.__table__).order_by(models.Menu.menu_id))


def read_orders(store_id: str, until: dt.datetime, since: dt.datetime | None = None) -> list[dict]:
    """since 이후(포함) until 까지(포함) 주문. 칸: order_id, ordered_at, channel, customer_key, total_amount"""
    order = models.Order
    statement = select(order.__table__).where(order.ordered_at <= until)
    if since is not None:
        statement = statement.where(order.ordered_at >= since)
    return _store_rows(store_id, statement.order_by(order.ordered_at))


def read_order_items(store_id: str, until: dt.datetime, since: dt.datetime | None = None) -> list[dict]:
    """같은 기간 주문에 들어간 메뉴. 칸: order_id, menu_id, quantity, unit_price"""
    order, item = models.Order, models.OrderItem
    statement = select(item.__table__).join(order, order.order_id == item.order_id).where(order.ordered_at <= until)
    if since is not None:
        statement = statement.where(order.ordered_at >= since)
    return _store_rows(store_id, statement)


def read_reviews(store_id: str, until: dt.datetime) -> list[dict]:
    """until 까지 쓰인 리뷰. 이어진 주문의 주문 방식과 주문 시각도 같이 붙인다.

    칸: review_id, order_id, customer_key, written_at, rating, content, complaint_type,
        order_channel(hall/delivery/None), ordered_at(None 이면 주문과 이어지지 않은 리뷰)
    """
    review, order = models.Review, models.Order
    statement = (
        select(
            review.__table__,
            order.channel.label("order_channel"),
            order.ordered_at.label("ordered_at"),
        )
        .outerjoin(order, order.order_id == review.order_id)
        .where(review.written_at <= until)
        .order_by(review.written_at)
    )
    rows = _store_rows(store_id, statement)
    # 사장님이 등록한 가게는 리뷰 불러오기 때 기록한 플랫폼(배민, 네이버, 쿠팡이츠)을 붙인다
    platforms = review_platforms(store_id)
    if platforms:
        for row in rows:
            row["platform"] = platforms.get(row["review_id"])
    # 리뷰 표에 플랫폼 칸이 없어 배달 리뷰는 배민으로 본다. 쿠팡이츠를 나누는 목업 가게는 배달 리뷰 일부를 쿠팡이츠로 정한다
    if store_id in COUPANG_SPLIT_STORES:
        for row in rows:
            if not row.get("platform") and row["order_channel"] == "delivery" and row["order_id"] % 10 < 3:
                row["platform"] = "COUPANG"
    return rows


def count_rows(store_id: str, until: dt.datetime) -> dict[str, int]:
    """until 까지 쌓인 주문·리뷰 수와 메뉴·알바 수 (개발자 대시보드 '매장' 탭). 행을 다 읽지 않고 세기만 한다."""
    order, review = models.Order, models.Review
    with store_engine(store_id).connect() as conn:
        return {
            "orders": conn.execute(select(func.count()).select_from(order).where(order.ordered_at <= until)).scalar(),
            "reviews": conn.execute(select(func.count()).select_from(review).where(review.written_at <= until)).scalar(),
            "menus": conn.execute(select(func.count()).select_from(models.Menu)).scalar(),
            "staff": conn.execute(select(func.count()).select_from(models.Staff)).scalar(),
        }


def read_staff(store_id: str) -> list[dict]:
    """알바 목록. 칸: staff_id, name, hourly_wage"""
    return _store_rows(store_id, select(models.Staff.__table__).order_by(models.Staff.staff_id))


def read_shifts(store_id: str, until: dt.datetime, since: dt.datetime | None = None) -> list[dict]:
    """근무 시작 시각이 기간 안인 근무. 칸: shift_id, staff_id, starts_at, ends_at"""
    shift = models.Shift
    statement = select(shift.__table__).where(shift.starts_at <= until)
    if since is not None:
        statement = statement.where(shift.starts_at >= since)
    return _store_rows(store_id, statement.order_by(shift.starts_at))


# ── 모든 가게 공통 ──


def read_events() -> list[dict]:
    """행사. 앞으로 열릴 행사도 미리 알 수 있으므로 기간을 자르지 않는다.
    칸: event_id, name, kind, starts_at, ends_at, lat, lng, distance_km"""
    return _common_rows(select(models.Event.__table__).order_by(models.Event.starts_at))


def read_games() -> list[dict]:
    """경기 일정. 칸: game_id, sport, level, title, starts_at"""
    return _common_rows(select(models.Game.__table__).order_by(models.Game.starts_at))


def read_weather(store_id: str | None = None) -> list[dict]:
    """날씨. 지난날은 관측, 앞날은 예보로 본다. 칸: date, temp_max, temp_min, precip_mm (값이 없으면 None)

    store_id 를 주면 기상청에서 받아 둔 그 가게 지역 날씨(store_weather_daily)를 쓴다.
    받은 적이 없으면(목업 가게, 인증키 없음) 모든 가게가 같이 쓰는 목업 날씨(weather_daily).
    목업 가게로 이은 실제 가게(s004 ...)는 주문이 1년치라, 받은 날만 기상청 날씨로 바꾸고 나머지 날은 목업 날씨를 쓴다.
    """
    common = _common_rows(select(models.WeatherDaily.__table__).order_by(models.WeatherDaily.date))
    if not store_id:
        return common
    rows = read_store_weather(store_id)
    if rows and registered_stores.is_mock_store(store_id):
        got = {r["date"] for r in rows}
        return sorted([r for r in common if r["date"] not in got] + rows, key=lambda r: r["date"])
    return rows or common


def weather_engine(store_id: str):
    """가게 날씨 표(store_weather_daily, store_weather_fetch)가 있는 곳. 목업 가게로 이은 가게는 따로 둔 파일."""
    return registered_stores.mock_weather_engine(store_id) if registered_stores.is_mock_store(store_id) else store_engine(store_id)


def _weather_rows(store_id: str, table) -> list[dict]:
    """가게 날씨 표의 행. 표가 아직 없으면(받은 적 없음) 빈 목록."""
    schema = None if registered_stores.is_mock_store(store_id) else store_id
    with weather_engine(store_id).connect() as conn:
        if not inspect(conn).has_table(table.__tablename__, schema=schema):
            return []
        return [dict(row._mapping) for row in conn.execute(select(table.__table__).order_by(*table.__table__.primary_key))]


def read_store_weather(store_id: str) -> list[dict]:
    """기상청에서 받아 둔 가게 지역 날씨 (app/weather/store_weather.py). 없으면 빈 목록.
    칸: date, kind(observed/forecast), source, temp_avg, temp_max, temp_min, sky, precip_type, precip_mm, pop_max, issued_at, fetched_at"""
    return _weather_rows(store_id, models.StoreWeatherDaily)


def read_store_weather_fetch(store_id: str) -> dict | None:
    """마지막으로 받은 기상청 날씨 전체. 칸: fetch_id, fetched_at, payload"""
    rows = _weather_rows(store_id, models.StoreWeatherFetch)
    return rows[0] if rows else None
