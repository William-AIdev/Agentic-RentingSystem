from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime, Integer, String, text
from sqlalchemy.dialects.postgresql import ENUM, TSTZRANGE
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.schema import FetchedValue

from services.order_types import OrderStatus


class Base(DeclarativeBase):
    pass


ORDER_STATUS_ENUM = ENUM(
    OrderStatus.RESERVED.value,
    OrderStatus.PAID.value,
    OrderStatus.SHIPPED.value,
    OrderStatus.OVERDUE.value,
    OrderStatus.SUCCESSFUL.value,
    OrderStatus.CANCELED.value,
    name="order_status",
    create_type=False,
)


class OrderModel(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    order_id: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    user_name: Mapped[str] = mapped_column(String, nullable=False)
    user_wechat: Mapped[str] = mapped_column(String, nullable=False)
    sku: Mapped[str] = mapped_column(String, nullable=False)
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    buffer_hours: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("3"))
    occupied: Mapped[object] = mapped_column(
        TSTZRANGE, nullable=False, server_default=FetchedValue()
    )
    status: Mapped[str] = mapped_column(
        ORDER_STATUS_ENUM,
        nullable=False,
        server_default=text("'reserved'::order_status"),
    )
    locker_code: Mapped[Optional[str]] = mapped_column(
        String, nullable=True, server_default=text("''")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
