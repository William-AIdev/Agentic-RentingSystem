from __future__ import annotations

from contextlib import nullcontext
from datetime import datetime, timedelta, timezone, tzinfo
from typing import Any, Dict, Optional

from psycopg import errors as pg_errors
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session
from services.db import create_db_client, get_session
from services.models import OrderModel
from services.order_types import (
    OCCUPYING_STATUSES,
    TERMINAL_STATUSES,
    ConflictError,
    ConstraintError,
    NotFoundError,
    Order,
    OrderStatus,
    TerminalOrderError,
    TimeRange,
    ValidationError,
)

# Default timezone for internal datetime handling in this module.
UTC_TZ: tzinfo = timezone.utc

# if not specified in DB
DEFAULT_BUFFER_HOURS = 3


def _to_utc(dt: datetime) -> datetime:
    """Ensure datetime is timezone-aware and normalized to UTC."""
    if dt.tzinfo is None:
        # Default naive datetimes to UTC for internal logic.
        return dt.replace(tzinfo=UTC_TZ)
    return dt.astimezone(UTC_TZ)


def _dt_to_iso_utc(dt: datetime) -> str:
    """Input: datetime. Returns ISO string for DB writes in UTC."""
    return _to_utc(dt).isoformat()


def _iso_to_dt_utc(value: datetime | str) -> datetime:
    """Accept datetime or ISO string and return UTC datetime."""
    if isinstance(value, datetime):
        return _to_utc(value)
    parsed = datetime.fromisoformat(value)
    return _to_utc(parsed)


def _model_to_order(row: OrderModel) -> Order:
    """Convert ORM model into Order dataclass."""
    return Order(
        order_id=row.order_id,
        user_name=row.user_name,
        user_wechat=row.user_wechat,
        sku=row.sku,
        start_at_iso=_iso_to_dt_utc(row.start_at),
        end_at_iso=_iso_to_dt_utc(row.end_at),
        buffer_hours=int(row.buffer_hours or 0),
        status=row.status,
        locker_code=row.locker_code,
        created_at=_iso_to_dt_utc(row.created_at),
        updated_at=_iso_to_dt_utc(row.updated_at),
    )


def _session_tx(session: Session):
    if session.in_transaction():
        return nullcontext()
    return session.begin()


def _get_data_from_db(order_id: str, client: Optional[Session] = None) -> Optional[OrderModel]:
    """Fetch ORM row by order_id; None if not found."""
    with get_session(client) as session:
        return session.execute(
            select(OrderModel).where(OrderModel.order_id == order_id).limit(1)
        ).scalar_one_or_none()


def _validate_time_range(start_at: datetime, end_at: datetime) -> None:
    """Ensure start < end; raise ValidationError otherwise."""
    if start_at >= end_at:
        raise ValidationError("start_at_iso must be earlier than end_at_iso")


def _merge_time_ranges(ranges: list[TimeRange]) -> list[TimeRange]:
    """Merge overlapping/adjacent time ranges. Input must be sorted by start."""
    if not ranges:
        return []
    merged = [ranges[0]]
    for current in ranges[1:]:
        last = merged[-1]
        if current.start_at <= last.end_at:
            merged[-1] = TimeRange(start_at=last.start_at, end_at=max(last.end_at, current.end_at))
        else:
            merged.append(current)
    return merged


def _format_slots_text(
    sku: str, window_start: datetime, window_end: datetime, slots: list[TimeRange]
) -> str:
    sku = sku.strip().upper()
    if not slots:
        return f"SKU {sku} 在 {window_start.isoformat()} 到 {window_end.isoformat()} 内无可供选择的时间段。"
    lines = [
        f"SKU {sku} 可供选择的时间段（{window_start.isoformat()} 至 {window_end.isoformat()}）："
    ]
    for slot in slots:
        lines.append(f"- {slot.start_at.isoformat()} 到 {slot.end_at.isoformat()}")
    return "\n".join(lines)


def suggest_time_slots_text(
    *,
    sku: str,
    expected_start_at: datetime | str,
    expected_end_at: datetime | str | None = None,
    client: Optional[Session] = None,
    window_days: int = 3,
) -> str:
    """
    Suggest available rental time slots within +/- window_days around expected time.
    User input without tzinfo is treated as UTC.
    Returns: human-readable text with available slots, timezone is Sydney.
    """
    sku = sku.strip().upper()
    expected_start = _iso_to_dt_utc(expected_start_at)
    if expected_end_at is None:
        expected_end = expected_start + timedelta(hours=3)  # default 3-hour renting slot
    else:
        expected_end = _iso_to_dt_utc(expected_end_at)
        _validate_time_range(expected_start, expected_end)

    # Clamp window days to [0, 7].
    window_days = max(0, min(7, window_days))
    duration = expected_end - expected_start

    # Earliest start is now; window range is expected_start - X to expected_end + X.
    window_start = expected_start - timedelta(days=window_days)
    now = datetime.now(tz=UTC_TZ)
    if window_start < now:
        window_start = now
    window_end = expected_end + timedelta(days=window_days)
    if window_end <= window_start:
        return _format_slots_text(sku, window_start, window_end, [])

    with get_session(client) as session:
        rows = (
            session.execute(
                select(OrderModel).where(
                    OrderModel.sku == sku,
                    OrderModel.status.in_(list(OCCUPYING_STATUSES)),
                )
            )
            .scalars()
            .all()
        )

    occupied: list[TimeRange] = []
    for row in rows:
        start_at = _iso_to_dt_utc(row.start_at)
        end_at = _iso_to_dt_utc(row.end_at)
        buffer_hours = int(row.buffer_hours or 0)
        if buffer_hours:
            start_at -= timedelta(hours=buffer_hours)
            end_at += timedelta(hours=buffer_hours)
        if end_at <= window_start or start_at >= window_end:
            continue
        occupied.append(TimeRange(start_at=start_at, end_at=end_at))

    occupied.sort(key=lambda r: r.start_at)
    merged = _merge_time_ranges(occupied)

    free_slots: list[TimeRange] = []
    cursor = window_start
    for block in merged:
        if cursor < block.start_at:
            free_slots.append(TimeRange(start_at=cursor, end_at=block.start_at))
        cursor = max(cursor, block.end_at)
    if cursor < window_end:
        free_slots.append(TimeRange(start_at=cursor, end_at=window_end))

    # Only keep slots that can fit the requested duration.
    filtered_slots = [slot for slot in free_slots if (slot.end_at - slot.start_at) >= duration]

    return _format_slots_text(sku, window_start, window_end, filtered_slots)


def add_order_to_db(
    *,
    order_id: str,
    user_name: str,
    user_wechat: str,
    sku: str,
    start_at: datetime,
    end_at: datetime,
    status: str,
    buffer_hours: Optional[int] = None,
    locker_code: Optional[str] = None,
    client: Optional[Session] = None,
) -> Order:
    """
    Insert a new order row to DB (default status is RESERVED).
    User input without tzinfo is treated as UTC.
    Inputs: basic order fields + optional locker_code/buffer_hours.
    Returns: created Order.
    """
    start_at_utc = _iso_to_dt_utc(start_at)
    end_at_utc = _iso_to_dt_utc(end_at)
    _validate_time_range(start_at_utc, end_at_utc)
    sku = sku.strip().upper()

    payload = {
        "order_id": order_id,
        "user_name": user_name,
        "user_wechat": user_wechat,
        "sku": sku,
        "start_at": start_at_utc,
        "end_at": end_at_utc,
        "status": status,
        "buffer_hours": buffer_hours if buffer_hours is not None else DEFAULT_BUFFER_HOURS,
        "locker_code": locker_code,
    }

    with get_session(client) as session:
        order = OrderModel(**payload)
        try:
            with _session_tx(session):
                session.add(order)
        except IntegrityError as exc:
            orig = getattr(exc, "orig", None)
            if isinstance(orig, pg_errors.ExclusionViolation):
                raise ConflictError(f"Order insert conflicted: {orig}", sku=sku) from exc
            if isinstance(orig, pg_errors.UniqueViolation):
                raise ConflictError(f"Order id already exists: {orig}", sku=sku) from exc
            if isinstance(orig, pg_errors.CheckViolation):
                raise ConstraintError(f"Failed to insert order: {orig}") from exc
            raise ConstraintError(f"Failed to insert order: {exc}") from exc
        except SQLAlchemyError as exc:
            raise ConstraintError(f"Failed to insert order: {exc}") from exc

        session.refresh(order)
        return _model_to_order(order)


def edit_order_from_db(
    order_id: str,
    *,
    patch: Dict[str, Any],
    client: Optional[Session] = None,
) -> Order:
    """
    Generic update helper; rejects terminal orders and invalid time ranges.
    Inputs: order_id and patch dict.
    Returns: updated Order.
    """
    if not patch:
        raise ValidationError("Patch cannot be empty")

    with get_session(client) as session:
        existing = _get_data_from_db(order_id, session)
        if not existing:
            raise NotFoundError(f"Order {order_id} not found")
        if existing.status in TERMINAL_STATUSES:
            raise TerminalOrderError(f"Order {order_id} is terminal and cannot be modified")

        if "start_at" in patch or "end_at" in patch:
            new_start = _iso_to_dt_utc(patch.get("start_at", existing.start_at))
            new_end = _iso_to_dt_utc(patch.get("end_at", existing.end_at))
            _validate_time_range(new_start, new_end)
            patch["start_at"] = new_start
            patch["end_at"] = new_end
        if "sku" in patch and patch["sku"] is not None:
            patch["sku"] = str(patch["sku"]).strip().upper()

        for key in ("created_at", "updated_at"):
            patch.pop(key, None)

        if not patch:
            raise ValidationError("Patch cannot be empty")

        try:
            with _session_tx(session):
                for key, value in patch.items():
                    setattr(existing, key, value)
        except IntegrityError as exc:
            orig = getattr(exc, "orig", None)
            if isinstance(orig, pg_errors.ExclusionViolation):
                raise ConflictError(
                    f"Order update conflicted: {orig}",
                    sku=existing.sku,
                ) from exc
            if isinstance(orig, pg_errors.CheckViolation):
                raise ConstraintError(f"Failed to update order: {orig}") from exc
            raise ConstraintError(f"Failed to update order: {exc}") from exc
        except SQLAlchemyError as exc:
            raise ConstraintError(f"Failed to update order: {exc}") from exc

        session.refresh(existing)
        return _model_to_order(existing)


def cancel_order(
    order_id: str,
    *,
    client: Optional[Session] = None,
    hard_delete: bool = False,
) -> Order:
    """
    Cancel an order (default: soft cancel via status). Set hard_delete=True to remove the row.
    Returns: canceled or deleted Order.
    """
    with get_session(client) as session:
        if hard_delete:
            existing = _get_data_from_db(order_id, session)
            if not existing:
                raise NotFoundError(f"Order {order_id} not found for delete")
            with _session_tx(session):
                session.delete(existing)
            return _model_to_order(existing)
        return edit_order_from_db(
            order_id, patch={"status": OrderStatus.CANCELED.value}, client=session
        )


def mark_order_paid(order_id: str, *, client: Optional[Session] = None) -> Order:
    """Move order to paid. Returns: updated Order."""
    return edit_order_from_db(order_id, patch={"status": OrderStatus.PAID.value}, client=client)


def finish_order(order_id: str, *, client: Optional[Session] = None) -> Order:
    """Mark order as finished/successful (terminal). Returns: updated Order."""
    return edit_order_from_db(
        order_id, patch={"status": OrderStatus.SUCCESSFUL.value}, client=client
    )


def deliver_order(
    order_id: str,
    *,
    locker_code: str,
    client: Optional[Session] = None,
) -> Order:
    """Mark order as shipped; locker_code is required. Returns: updated Order."""
    if not locker_code:
        raise ValidationError("locker_code is required when marking as shipped")
    return edit_order_from_db(
        order_id,
        patch={"status": OrderStatus.SHIPPED.value, "locker_code": locker_code},
        client=client,
    )


def get_order_detail(order_id: str, *, client: Optional[Session] = None) -> Order:
    """Fetch order detail by id. Returns: Order or raises NotFoundError."""
    row = _get_data_from_db(order_id, client)
    if not row:
        raise NotFoundError(f"Order {order_id} not found")
    return _model_to_order(row)


def order_to_text(order: Order, *, tz: tzinfo = UTC_TZ) -> str:
    """Convert Order dataclass to human-readable text."""

    def _fmt(dt: datetime) -> str:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC_TZ)
        return dt.astimezone(tz).isoformat()

    lines = [
        f"Order ID: {order.order_id}",
        f"User Name: {order.user_name}",
        f"WeChat: {order.user_wechat}",
        f"SKU: {order.sku}",
        f"Start At: {_fmt(order.start_at_iso)}",
        f"End At: {_fmt(order.end_at_iso)}",
        f"Buffer Hours: {order.buffer_hours}",
        f"Status: {order.status}",
        f"Locker Code: {order.locker_code or 'N/A'}",
        f"Created At: {_fmt(order.created_at)}",
        f"Updated At: {_fmt(order.updated_at)}",
    ]
    return "\n".join(lines)
