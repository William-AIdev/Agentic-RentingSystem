from __future__ import annotations

from datetime import datetime, timedelta, timezone, tzinfo
from typing import Any, Dict, Optional

import psycopg
from psycopg import errors as pg_errors

from services.db import create_db_client, get_conn
from services.types import (
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


def _data_to_order(row: Dict[str, Any]) -> Order:
    """Convert DB row dict into Order dataclass."""
    return Order(
        order_id=row["order_id"],
        user_name=row["user_name"],
        user_wechat=row["user_wechat"],
        sku=row["sku"],
        start_at_iso=_iso_to_dt_utc(row["start_at"]),
        end_at_iso=_iso_to_dt_utc(row["end_at"]),
        buffer_hours=int(row.get("buffer_hours") or 0),
        status=row["status"],
        locker_code=row.get("locker_code"),
        created_at=_iso_to_dt_utc(row["created_at"]),
        updated_at=_iso_to_dt_utc(row["updated_at"]),
    )


def _get_data_from_db(order_id: str, client: Optional[psycopg.Connection] = None) -> Dict[str, Any]:
    """Fetch raw row dict by order_id; empty dict if not found."""
    with get_conn(client) as db:
        row = db.execute(
            "SELECT * FROM orders WHERE order_id = %s LIMIT 1",
            (order_id,),
        ).fetchone()
        return dict(row) if row else {}


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


def _format_slots_text(sku: str, window_start: datetime, window_end: datetime, slots: list[TimeRange]) -> str:
    sku = sku.strip().upper()
    if not slots:
        return (
            f"SKU {sku} 在 {window_start.isoformat()} 到 {window_end.isoformat()} 内无可供选择的时间段。"
        )
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
    client: Optional[psycopg.Connection] = None,
    window_days: int = 3,
) -> str:
    """
    Suggest available rental time slots within +/- window_days around expected time.
    User input without tzinfo is treated as UTC.
    Returns: human-readable text with available slots.
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

    with get_conn(client) as db:
        rows = db.execute(
            """
            SELECT * FROM orders
            WHERE sku = %s AND status = ANY(%s)
            """,
            (sku, list(OCCUPYING_STATUSES)),
        ).fetchall()

    occupied: list[TimeRange] = []
    for row in rows:
        start_at = _iso_to_dt_utc(row["start_at"])
        end_at = _iso_to_dt_utc(row["end_at"])
        buffer_hours = int(row.get("buffer_hours") or 0)
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
    filtered_slots = [
        slot for slot in free_slots if (slot.end_at - slot.start_at) >= duration
    ]

    return _format_slots_text(sku, window_start, window_end, filtered_slots)


def add_order_to_db(
    *,
    order_id: str,
    user_name: str,
    user_wechat: str,
    sku: str,
    start_at: datetime,
    end_at: datetime,
    status: str = OrderStatus.RESERVED.value,
    buffer_hours: Optional[int] = None,
    locker_code: Optional[str] = None,
    client: Optional[psycopg.Connection] = None,
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

    with get_conn(client) as db:
        try:
            row = db.execute(
                """
                INSERT INTO orders (
                    order_id, user_name, user_wechat, sku, start_at, end_at,
                    status, buffer_hours, locker_code
                )
                VALUES (%(order_id)s, %(user_name)s, %(user_wechat)s, %(sku)s, %(start_at)s, %(end_at)s,
                        %(status)s, %(buffer_hours)s, %(locker_code)s)
                RETURNING *
                """,
                payload,
            ).fetchone()
        except pg_errors.ExclusionViolation as exc:
            raise ConflictError(f"Order insert conflicted: {exc}", sku=sku) from exc
        except pg_errors.UniqueViolation as exc:
            raise ConflictError(f"Order id already exists: {exc}", sku=sku) from exc
        except pg_errors.CheckViolation as exc:
            raise ConstraintError(f"Failed to insert order: {exc}") from exc
        except psycopg.Error as exc:
            raise ConstraintError(f"Failed to insert order: {exc}") from exc

    if not row:
        raise ConflictError("Order insert failed or conflicted", sku=sku)
    return _data_to_order(dict(row))


def edit_order_from_db(
    order_id: str,
    *,
    patch: Dict[str, Any],
    client: Optional[psycopg.Connection] = None,
) -> Order:
    """
    Generic update helper; rejects terminal orders and invalid time ranges.
    Inputs: order_id and patch dict.
    Returns: updated Order.
    """
    if not patch:
        raise ValidationError("Patch cannot be empty")

    with get_conn(client) as db:
        existing = _get_data_from_db(order_id, db)
        if not existing:
            raise NotFoundError(f"Order {order_id} not found")
        if existing["status"] in TERMINAL_STATUSES:
            raise TerminalOrderError(f"Order {order_id} is terminal and cannot be modified")

        if "start_at" in patch or "end_at" in patch:
            new_start = _iso_to_dt_utc(patch.get("start_at", existing["start_at"]))
            new_end = _iso_to_dt_utc(patch.get("end_at", existing["end_at"]))
            _validate_time_range(new_start, new_end)
            patch["start_at"] = new_start
            patch["end_at"] = new_end
        if "sku" in patch and patch["sku"] is not None:
            patch["sku"] = str(patch["sku"]).strip().upper()

        for key in ("created_at", "updated_at"):
            patch.pop(key, None)

        fields = []
        values = []
        for key, value in patch.items():
            fields.append(f"{key} = %s")
            values.append(value)
        if not fields:
            raise ValidationError("Patch cannot be empty")

        values.append(order_id)

        try:
            row = db.execute(
                f"UPDATE orders SET {', '.join(fields)} WHERE order_id = %s RETURNING *",
                values,
            ).fetchone()
        except pg_errors.ExclusionViolation as exc:
            raise ConflictError(f"Order update conflicted: {exc}", sku=existing.get("sku")) from exc
        except pg_errors.CheckViolation as exc:
            raise ConstraintError(f"Failed to update order: {exc}") from exc
        except psycopg.Error as exc:
            raise ConstraintError(f"Failed to update order: {exc}") from exc

    if not row:
        raise ConflictError("Order update failed or conflicted", sku=existing.get("sku"))
    return _data_to_order(dict(row))


def cancel_order(
    order_id: str,
    *,
    client: Optional[psycopg.Connection] = None,
    hard_delete: bool = False,
) -> Order:
    """
    Cancel an order (default: soft cancel via status). Set hard_delete=True to remove the row.
    Returns: canceled or deleted Order.
    """
    with get_conn(client) as db:
        if hard_delete:
            row = db.execute(
                "DELETE FROM orders WHERE order_id = %s RETURNING *",
                (order_id,),
            ).fetchone()
            if not row:
                raise NotFoundError(f"Order {order_id} not found for delete")
            return _data_to_order(dict(row))
        return edit_order_from_db(order_id, patch={"status": OrderStatus.CANCELED.value}, client=db)


def mark_order_paid(order_id: str, *, client: Optional[psycopg.Connection] = None) -> Order:
    """Move order to paid. Returns: updated Order."""
    return edit_order_from_db(order_id, patch={"status": OrderStatus.PAID.value}, client=client)


def finish_order(order_id: str, *, client: Optional[psycopg.Connection] = None) -> Order:
    """Mark order as finished/successful (terminal). Returns: updated Order."""
    return edit_order_from_db(order_id, patch={"status": OrderStatus.SUCCESSFUL.value}, client=client)


def deliver_order(
    order_id: str,
    *,
    locker_code: str,
    client: Optional[psycopg.Connection] = None,
) -> Order:
    """Mark order as shipped; locker_code is required. Returns: updated Order."""
    if not locker_code:
        raise ValidationError("locker_code is required when marking as shipped")
    return edit_order_from_db(
        order_id,
        patch={"status": OrderStatus.SHIPPED.value, "locker_code": locker_code},
        client=client,
    )


def get_order_detail(order_id: str, *, client: Optional[psycopg.Connection] = None) -> Order:
    """Fetch order detail by id. Returns: Order or raises NotFoundError."""
    row = _get_data_from_db(order_id, client)
    if not row:
        raise NotFoundError(f"Order {order_id} not found")
    return _data_to_order(row)


def order_to_text(order: Order) -> str:
    """Convert Order dataclass to human-readable text."""
    lines = [
        f"Order ID: {order.order_id}",
        f"User Name: {order.user_name}",
        f"WeChat: {order.user_wechat}",
        f"SKU: {order.sku}",
        f"Start At: {order.start_at_iso.isoformat()}",
        f"End At: {order.end_at_iso.isoformat()}",
        f"Buffer Hours: {order.buffer_hours}",
        f"Status: {order.status}",
        f"Locker Code: {order.locker_code or 'N/A'}",
        f"Created At: {order.created_at.isoformat()}",
        f"Updated At: {order.updated_at.isoformat()}",
    ]
    return "\n".join(lines)
