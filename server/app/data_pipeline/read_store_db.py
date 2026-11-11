"""DB(지호) 읽기. 서버에서 DB 에 들어가는 문은 이 파일 하나다.

- 가게 전용 테이블(store, menu, orders, order_items, reviews, staff, shifts)은 store_id 로 그 가게 것만 읽는다.
  나중에 로그인이 생기면 '이 사장님이 이 가게를 볼 수 있는지' 검사도 여기 들어오기 전에 한 번만 하면 된다.
- 공통 테이블(events, games, weather_daily)은 모든 가게가 같이 쓴다.
- until 을 받는 함수는 그 시각까지 생긴 행만 돌려준다. 목업 DB 에는 12/31 까지 주문이 들어 있어서
  미래 데이터를 꺼내지 않도록 여기서 막는다.
- 돌려주는 값은 DB 칸 이름 그대로의 dict 목록이다. 분석이나 화면 모양으로 바꾸는 일은 다른 파일이 한다.
"""

import datetime as dt

from sqlalchemy import select

from db import models
from db.session import engine, store_db_files, store_engine


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
    return _store_rows(store_id, statement)


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


def read_weather() -> list[dict]:
    """날씨. 지난날은 관측, 앞날은 예보로 본다. 칸: date, temp_max, temp_min, precip_mm"""
    return _common_rows(select(models.WeatherDaily.__table__).order_by(models.WeatherDaily.date))
