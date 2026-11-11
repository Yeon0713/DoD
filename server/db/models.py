"""C1 원본 테이블."""

import datetime as dt

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
    Time,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

TZ = DateTime(timezone=True)


class Base(DeclarativeBase):
    pass


class Store(Base):
    __tablename__ = "store"

    store_id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(Text)
    address: Mapped[str] = mapped_column(Text)
    lat: Mapped[float] = mapped_column(Double)
    lng: Mapped[float] = mapped_column(Double)
    open_time: Mapped[dt.time] = mapped_column(Time)
    close_time: Mapped[dt.time] = mapped_column(Time)
    closed_weekdays: Mapped[list] = mapped_column(JSONB)
    slots: Mapped[list] = mapped_column(JSONB)


class Menu(Base):
    __tablename__ = "menu"
    __table_args__ = (CheckConstraint("category IN ('main','side','drink')"),)

    menu_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    store_id: Mapped[str] = mapped_column(ForeignKey("store.store_id"))
    name: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(Text)
    price: Mapped[int] = mapped_column(Integer)


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (CheckConstraint("channel IN ('hall','delivery')"),)

    order_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    store_id: Mapped[str] = mapped_column(ForeignKey("store.store_id"))
    ordered_at: Mapped[dt.datetime] = mapped_column(TZ, index=True)
    channel: Mapped[str] = mapped_column(Text)
    customer_key: Mapped[str | None] = mapped_column(Text, index=True)
    total_amount: Mapped[int] = mapped_column(Integer)


class OrderItem(Base):
    __tablename__ = "order_items"

    order_id: Mapped[int] = mapped_column(ForeignKey("orders.order_id"), primary_key=True)
    menu_id: Mapped[int] = mapped_column(ForeignKey("menu.menu_id"), primary_key=True)
    quantity: Mapped[int] = mapped_column(Integer)
    unit_price: Mapped[int] = mapped_column(Integer)


class Review(Base):
    __tablename__ = "reviews"
    __table_args__ = (
        CheckConstraint("rating BETWEEN 1 AND 5"),
        CheckConstraint("complaint_type IN ('none','delivery_delay','taste')"),
    )

    review_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    store_id: Mapped[str] = mapped_column(ForeignKey("store.store_id"))
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.order_id"))
    customer_key: Mapped[str | None] = mapped_column(Text, index=True)
    written_at: Mapped[dt.datetime] = mapped_column(TZ, index=True)
    rating: Mapped[int] = mapped_column(SmallInteger)
    content: Mapped[str] = mapped_column(Text)
    # 목업에서는 비워 둔다. LLM 이 리뷰를 읽고 채운다.
    complaint_type: Mapped[str | None] = mapped_column(Text)


class Staff(Base):
    __tablename__ = "staff"

    staff_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    store_id: Mapped[str] = mapped_column(ForeignKey("store.store_id"))
    name: Mapped[str] = mapped_column(Text)
    hourly_wage: Mapped[int] = mapped_column(Integer)


class Shift(Base):
    __tablename__ = "shifts"

    shift_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    staff_id: Mapped[int] = mapped_column(ForeignKey("staff.staff_id"))
    starts_at: Mapped[dt.datetime] = mapped_column(TZ)
    ends_at: Mapped[dt.datetime] = mapped_column(TZ)


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
