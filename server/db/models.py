"""C1 원본 테이블.

- 매장 전용 테이블(store, menu, orders, order_items, reviews, staff, shifts)은 매장마다 따로 있다.
  개발 DB(SQLite)에서는 매장 파일 db/data/s001.db 를 s001 이라는 이름으로 붙여서 s001.orders 처럼 쓴다.
  모델에는 자리표시 스키마 STORE_SCHEMA 를 적어 두고, 쓸 때 실제 매장 이름으로 바꾼다 (db.session.store_engine).
- 모든 매장이 함께 쓰는 테이블(events, games, weather_daily)은 db/data/common.db 에 하나만 있다.
- 배포 때 PostgreSQL 로 옮길 수 있게 DB 공통 타입만 쓴다. 매장은 그때 PostgreSQL 스키마(s001 ...)가 된다.
"""

import datetime as dt
from zoneinfo import ZoneInfo

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    Double,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    Text,
    JSON,
    Time,
    TypeDecorator,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

KST = ZoneInfo("Asia/Seoul")


class KSTDateTime(TypeDecorator):
    """시각은 서울 시간으로 저장하고, 읽으면 서울 시간대가 붙은 datetime 이 나온다.

    SQLite 는 시간대를 저장하지 않으므로 서울 시간으로 바꿔 시간대를 떼고 저장한다.
    시간대 없는 값을 넣으면 서울 시간으로 본다.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        value = value.astimezone(KST) if value.tzinfo else value.replace(tzinfo=KST)
        return value.replace(tzinfo=None) if dialect.name == "sqlite" else value

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return value.replace(tzinfo=KST) if value.tzinfo is None else value.astimezone(KST)


TZ = KSTDateTime()
STORE_SCHEMA = "store_schema"  # 자리표시. 실행할 때 매장 스키마 이름(s001 ...)으로 바뀐다.
STORE_TABLES = ["store", "menu", "staff", "shifts", "orders", "order_items", "reviews"]  # 부모 테이블부터
COMMON_TABLES = ["events", "games", "weather_daily"]


class Base(DeclarativeBase):
    pass


# ── 매장 전용 ──────────────────────────────────────────
class Store(Base):
    """매장 정보. 매장 스키마마다 1행."""

    __tablename__ = "store"
    __table_args__ = {"schema": STORE_SCHEMA}

    store_id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(Text)
    address: Mapped[str] = mapped_column(Text)
    lat: Mapped[float] = mapped_column(Double)
    lng: Mapped[float] = mapped_column(Double)
    open_time: Mapped[dt.time] = mapped_column(Time)
    close_time: Mapped[dt.time] = mapped_column(Time)
    closed_weekdays: Mapped[list] = mapped_column(JSON)
    slots: Mapped[list] = mapped_column(JSON)


class Menu(Base):
    __tablename__ = "menu"
    __table_args__ = (CheckConstraint("category IN ('main','side','drink')"), {"schema": STORE_SCHEMA})

    menu_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(Text)
    price: Mapped[int] = mapped_column(Integer)


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (CheckConstraint("channel IN ('hall','delivery')"), {"schema": STORE_SCHEMA})

    order_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    ordered_at: Mapped[dt.datetime] = mapped_column(TZ, index=True)
    channel: Mapped[str] = mapped_column(Text)
    customer_key: Mapped[str | None] = mapped_column(Text, index=True)
    total_amount: Mapped[int] = mapped_column(Integer)


class OrderItem(Base):
    __tablename__ = "order_items"
    __table_args__ = {"schema": STORE_SCHEMA}

    order_id: Mapped[int] = mapped_column(ForeignKey(f"{STORE_SCHEMA}.orders.order_id"), primary_key=True)
    menu_id: Mapped[int] = mapped_column(ForeignKey(f"{STORE_SCHEMA}.menu.menu_id"), primary_key=True)
    quantity: Mapped[int] = mapped_column(Integer)
    unit_price: Mapped[int] = mapped_column(Integer)


class Review(Base):
    __tablename__ = "reviews"
    __table_args__ = (
        CheckConstraint("rating BETWEEN 1 AND 5"),
        CheckConstraint("complaint_type IN ('none','delivery_delay','taste')"),
        {"schema": STORE_SCHEMA},
    )

    review_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    order_id: Mapped[int | None] = mapped_column(ForeignKey(f"{STORE_SCHEMA}.orders.order_id"))
    customer_key: Mapped[str | None] = mapped_column(Text, index=True)
    written_at: Mapped[dt.datetime] = mapped_column(TZ, index=True)
    rating: Mapped[int] = mapped_column(SmallInteger)
    content: Mapped[str] = mapped_column(Text)
    # 목업에서는 비워 둔다. LLM 이 리뷰를 읽고 채운다.
    complaint_type: Mapped[str | None] = mapped_column(Text)


class Staff(Base):
    __tablename__ = "staff"
    __table_args__ = {"schema": STORE_SCHEMA}

    staff_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    hourly_wage: Mapped[int] = mapped_column(Integer)


class Shift(Base):
    __tablename__ = "shifts"
    __table_args__ = {"schema": STORE_SCHEMA}

    shift_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    staff_id: Mapped[int] = mapped_column(ForeignKey(f"{STORE_SCHEMA}.staff.staff_id"))
    starts_at: Mapped[dt.datetime] = mapped_column(TZ)
    ends_at: Mapped[dt.datetime] = mapped_column(TZ)


# ── 모든 매장 공통 (public) ─────────────────────────────
class Event(Base):
    __tablename__ = "events"
    __table_args__ = (
        CheckConstraint("kind IN ('univ_festival','local_festival','marathon','other')"),
    )

    event_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(Text)
    starts_at: Mapped[dt.datetime] = mapped_column(TZ)
    ends_at: Mapped[dt.datetime] = mapped_column(TZ)
    lat: Mapped[float] = mapped_column(Double)
    lng: Mapped[float] = mapped_column(Double)
    distance_km: Mapped[float] = mapped_column(Numeric(5, 2))


class Game(Base):
    __tablename__ = "games"
    __table_args__ = (
        CheckConstraint("sport IN ('soccer','baseball')"),
        CheckConstraint("level IN ('national','pro')"),
    )

    game_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sport: Mapped[str] = mapped_column(Text)
    level: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    starts_at: Mapped[dt.datetime] = mapped_column(TZ)


class WeatherDaily(Base):
    __tablename__ = "weather_daily"

    date: Mapped[dt.date] = mapped_column(Date, primary_key=True)
    temp_max: Mapped[float] = mapped_column(Numeric(4, 1))
    temp_min: Mapped[float] = mapped_column(Numeric(4, 1))
    precip_mm: Mapped[float] = mapped_column(Numeric(5, 1))
