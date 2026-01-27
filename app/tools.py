from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Dict
from zoneinfo import ZoneInfo

from langchain_core.tools import tool

from app.rag import rules_rag
from app.config import settings
from services.order_services import (
    add_order_to_db,
    cancel_order,
    deliver_order,
    edit_order_from_db,
    finish_order,
    get_order_detail,
    mark_order_paid,
    order_to_text,
    suggest_time_slots_text,
)
from services.order_types import (
    ConflictError,
    ConstraintError,
    NotFoundError,
    OrderStatus,
    TerminalOrderError,
    ValidationError,
)

# Default input/output timezone is configurable (default Australia/Sydney).
LOCAL_TZ = ZoneInfo(settings.local_timezone)
UTC_TZ = timezone.utc


def _order_to_dict(order) -> Dict[str, Any]:
    return asdict(order)


def _to_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=LOCAL_TZ)
    return dt.astimezone(UTC_TZ)


def _parse_local_time(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        return _to_utc(value)
    return _to_utc(datetime.fromisoformat(value))


def _to_local(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC_TZ)
    return dt.astimezone(LOCAL_TZ)


def _order_to_local_dict(order) -> Dict[str, Any]:
    data = asdict(order)
    for key in ("start_at_iso", "end_at_iso", "created_at", "updated_at"):
        if key in data and isinstance(data[key], datetime):
            data[key] = _to_local(data[key]).isoformat()
    return data


def _normalize_patch(patch: Dict[str, Any]) -> Dict[str, Any]:
    if "start_at" in patch and isinstance(patch["start_at"], str):
        patch["start_at"] = _parse_local_time(patch["start_at"])
    if "end_at" in patch and isinstance(patch["end_at"], str):
        patch["end_at"] = _parse_local_time(patch["end_at"])
    return patch


@tool
def create_order_tool(
    *,
    order_id: str,
    user_name: str,
    user_wechat: str,
    sku: str,
    start_at: str,
    end_at: str,
    status: str | None = None,
    buffer_hours: int | None = None,
    locker_code: str | None = None,
) -> Dict[str, Any]:
    """Create an order."""
    try:
        order = add_order_to_db(
            order_id=order_id,
            user_name=user_name,
            user_wechat=user_wechat,
            sku=sku,
            start_at=_parse_local_time(start_at),
            end_at=_parse_local_time(end_at),
            status=status if status is not None else OrderStatus.RESERVED.value,
            buffer_hours=buffer_hours,
            locker_code=locker_code,
        )
        return {"result": _order_to_local_dict(order)}
    except (ConflictError, ConstraintError, ValidationError, ValueError) as exc:
        return {"error": f"{exc.__class__.__name__}: {exc}"}


@tool
def get_order_tool(*, order_id: str) -> Dict[str, Any]:
    """Get order detail."""
    try:
        order = get_order_detail(order_id)
        return {"result": order_to_text(order, tz=LOCAL_TZ)}
    except NotFoundError as exc:
        return {"error": f"{exc.__class__.__name__}: {exc}"}


@tool
def update_order_tool(*, order_id: str, patch: Dict[str, Any]) -> Dict[str, Any]:
    """Update order by patch."""
    try:
        normalized = _normalize_patch(dict(patch))
        order = edit_order_from_db(order_id, patch=normalized)
        return {"result": _order_to_local_dict(order)}
    except (
        ConflictError,
        ConstraintError,
        ValidationError,
        NotFoundError,
        TerminalOrderError,
    ) as exc:
        return {"error": f"{exc.__class__.__name__}: {exc}"}


@tool
def cancel_order_tool(*, order_id: str, hard_delete: bool = False) -> Dict[str, Any]:
    """Cancel order."""
    try:
        order = cancel_order(order_id, hard_delete=hard_delete)
        return {"result": _order_to_local_dict(order)}
    except (NotFoundError, ValidationError, TerminalOrderError) as exc:
        return {"error": f"{exc.__class__.__name__}: {exc}"}


@tool
def mark_paid_tool(*, order_id: str) -> Dict[str, Any]:
    """Mark order paid."""
    try:
        order = mark_order_paid(order_id)
        return {"result": _order_to_local_dict(order)}
    except (NotFoundError, ValidationError, TerminalOrderError) as exc:
        return {"error": f"{exc.__class__.__name__}: {exc}"}


@tool
def deliver_order_tool(*, order_id: str, locker_code: str) -> Dict[str, Any]:
    """Deliver order with locker_code."""
    try:
        order = deliver_order(order_id, locker_code=locker_code)
        return {"result": _order_to_local_dict(order)}
    except (NotFoundError, ValidationError, ConstraintError, TerminalOrderError) as exc:
        return {"error": f"{exc.__class__.__name__}: {exc}"}


@tool
def finish_order_tool(*, order_id: str) -> Dict[str, Any]:
    """Finish order."""
    try:
        order = finish_order(order_id)
        return {"result": _order_to_local_dict(order)}
    except (NotFoundError, ValidationError, TerminalOrderError) as exc:
        return {"error": f"{exc.__class__.__name__}: {exc}"}


@tool
def suggest_time_slots_tool(
    *,
    sku: str,
    expected_start_at: str,
    expected_end_at: str | None = None,
    window_days: int = 3,
) -> Dict[str, Any]:
    """Suggest available rental time slots around an expected time window."""
    try:
        text = suggest_time_slots_text(
            sku=sku,
            expected_start_at=_parse_local_time(expected_start_at),
            expected_end_at=_parse_local_time(expected_end_at) if expected_end_at else None,
            window_days=window_days,
        )
        return {"result": text}
    except (ValidationError, ValueError) as exc:
        return {"error": f"{exc.__class__.__name__}: {exc}"}


@tool
def rag_rules_tool(*, question: str) -> Dict[str, Any]:
    """基于本地规则文件回答客户的规则/流程/计费/押金等问题。如果返回了正在初始化，则直接回复让客户稍后再试。"""
    if not rules_rag.ready:
        return {"result": "规则库正在初始化，请稍后再试。"}
    snippets = rules_rag.query(question)
    if not snippets:
        error = rules_rag.error
        if error:
            return {"result": f"规则库未就绪：{error}"}
        return {"result": "规则库未命中相关条目。"}
    ctx = "\n".join(f"- {s}" for s in snippets)
    return {"result": f"在文件中查到的相关规则如下：\n{ctx}\n\n"}


TOOLS = [
    rag_rules_tool,
    create_order_tool,
    get_order_tool,
    update_order_tool,
    cancel_order_tool,
    mark_paid_tool,
    deliver_order_tool,
    finish_order_tool,
    suggest_time_slots_tool,
]
