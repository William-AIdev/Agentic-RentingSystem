from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Dict, Optional

from dotenv import load_dotenv
from supabase import Client, create_client
from supabase.lib.client_options import ClientOptions

from services.types import (
    TERMINAL_STATUSES,
    ConflictError,
    ConstraintError,
    NotFoundError,
    Order,
    OrderStatus,
    TerminalOrderError,
    ValidationError,
)

load_dotenv()

# if not specified in DB
DEFAULT_BUFFER_HOURS = 3


def _create_client() -> Client:
    """
    Create a supabase client using the service role key when present.
    Returns: supabase Client configured for server-side use.
    """
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_ANON_KEY")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_*_KEY are required")
    return create_client(
        url,
        key,
        options=ClientOptions(auto_refresh_token=False, persist_session=False),
    )


def _dt_to_iso(dt: datetime) -> str:
    """Input: datetime. Returns ISO string for DB writes."""
    return dt.isoformat()


def _parse_dt(value: datetime | str) -> datetime: # todo: works in py3.10+?
    """Accept datetime or ISO string and return datetime."""
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value)


def _row_to_order(row: Dict[str, Any]) -> Order:
    """Convert DB row dict into Order dataclass."""
    return Order(
        order_id=row["order_id"],
        user_name=row["user_name"],
        user_wechat=row["user_wechat"],
        sku=row["sku"],
        start_at=_parse_dt(row["start_at"]),
        end_at=_parse_dt(row["end_at"]),
        buffer_hours=int(row.get("buffer_hours") or 0),
        status=row["status"],
        locker_code=row.get("locker_code"),
        created_at=_parse_dt(row["created_at"]),
        updated_at=_parse_dt(row["updated_at"]),
    )


def _get_order_row(order_id: str, client: Optional[Client] = None) -> Dict[str, Any]:
    """Fetch raw row dict by order_id; empty dict if not found."""
    sb = client or _create_client()
    resp = sb.table("orders").select("*").eq("order_id", order_id).limit(1).execute()
    data = getattr(resp, "data", None)
    if data:
        return data[0]
    return {}


def _validate_time_range(start_at: datetime, end_at: datetime) -> None:
    """Ensure start < end; raise ValidationError otherwise."""
    if start_at >= end_at:
        raise ValidationError("start_at must be earlier than end_at")


def add_order(
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
        client: Optional[Client] = None,
) -> Order:
    """
    Insert a new order row to DB (default status RESERVED).
    Inputs: basic order fields + optional locker_code/buffer_hours.
    Returns: created Order.
    """
    _validate_time_range(start_at, end_at)
    sb = client or _create_client()
    payload = {
        "order_id": order_id,
        "user_name": user_name,
        "user_wechat": user_wechat,
        "sku": sku,
        "start_at": _dt_to_iso(start_at),
        "end_at": _dt_to_iso(end_at),
        "status": status,
        "buffer_hours": buffer_hours if buffer_hours is not None else DEFAULT_BUFFER_HOURS,
    }
    if locker_code is not None:
        payload["locker_code"] = locker_code
    try:
        resp = sb.table("orders").insert(payload).execute()
    except Exception as exc:
        raise ConstraintError(f"Failed to insert order: {exc}") from exc

    data = getattr(resp, "data", None) or []
    if not data:
        raise ConflictError("Order insert failed or conflicted", sku=sku)
    return _row_to_order(data[0])


def edit_order(
        order_id: str,
        *,
        patch: Dict[str, Any],
        client: Optional[Client] = None,
) -> Order:
    """
    Generic update helper; rejects terminal orders and invalid time ranges.
    Inputs: order_id and patch dict.
    Returns: updated Order.
    """
    if not patch:
        raise ValidationError("Patch cannot be empty")
    sb = client or _create_client()
    existing = _get_order_row(order_id, sb)
    if not existing:
        raise NotFoundError(f"Order {order_id} not found")
    if existing["status"] in TERMINAL_STATUSES:
        raise TerminalOrderError(f"Order {order_id} is terminal and cannot be modified")

    if "start_at" in patch or "end_at" in patch:
        new_start = _parse_dt(patch.get("start_at", existing["start_at"]))
        new_end = _parse_dt(patch.get("end_at", existing["end_at"]))
        _validate_time_range(new_start, new_end)
        patch["start_at"] = _dt_to_iso(new_start)
        patch["end_at"] = _dt_to_iso(new_end)

    for key in ("created_at", "updated_at"):
        patch.pop(key, None)

    try:
        resp = sb.table("orders").update(patch).eq("order_id", order_id).execute()
    except Exception as exc:
        message = str(exc)
        if "overlap" in message or "conflict" in message:
            raise ConflictError(f"Order update conflicted: {message}", sku=existing.get("sku")) from exc
        raise ConstraintError(f"Failed to update order: {message}") from exc

    data = getattr(resp, "data", None) or []
    if not data:
        raise ConflictError("Order update failed or conflicted", sku=existing.get("sku"))
    return _row_to_order(data[0])


def cancel_order(order_id: str, *, client: Optional[Client] = None, hard_delete: bool = False) -> Order:
    """
    Cancel an order (default: soft cancel via status). Set hard_delete=True to remove the row.
    Returns: canceled or deleted Order.
    """
    sb = client or _create_client()
    if hard_delete:
        resp = sb.table("orders").delete().eq("order_id", order_id).execute()
        data = getattr(resp, "data", None) or []
        if not data:
            raise NotFoundError(f"Order {order_id} not found for delete")
        return _row_to_order(data[0])
    return edit_order(order_id, patch={"status": OrderStatus.CANCELED.value}, client=sb)


def mark_order_paid(order_id: str, *, client: Optional[Client] = None) -> Order:
    """Move order to paid. Returns: updated Order."""
    return edit_order(order_id, patch={"status": OrderStatus.PAID.value}, client=client)


def finish_order(order_id: str, *, client: Optional[Client] = None) -> Order:
    """Mark order as finished/successful (terminal). Returns: updated Order."""
    return edit_order(order_id, patch={"status": OrderStatus.SUCCESSFUL.value}, client=client)


def deliver_order(
        order_id: str,
        *,
        locker_code: str,
        client: Optional[Client] = None,
) -> Order:
    """Mark order as shipped; locker_code is required. Returns: updated Order."""
    if not locker_code:
        raise ValidationError("locker_code is required when marking as shipped")
    return edit_order(
        order_id,
        patch={"status": OrderStatus.SHIPPED.value, "locker_code": locker_code},
        client=client,
    )


def get_order_detail(order_id: str, *, client: Optional[Client] = None) -> Order:
    """Fetch order detail by id. Returns: Order or raises NotFoundError."""
    row = _get_order_row(order_id, client)
    if not row:
        raise NotFoundError(f"Order {order_id} not found")
    return _row_to_order(row)
