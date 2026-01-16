from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Iterable, List, Optional, Tuple, TypedDict, Literal

# =========
# Domain Types
# =========

class OrderStatus(str, Enum):
    RESERVED = "reserved"
    PAID = "paid"
    SHIPPED = "shipped"
    OVERDUE = "overdue"
    SUCCESSFUL = "successful"   # terminal
    CANCELED = "canceled"       # terminal


TERMINAL_STATUSES = {
    OrderStatus.SUCCESSFUL.value, 
    OrderStatus.CANCELED.value
}
OCCUPYING_STATUSES = {
    OrderStatus.RESERVED.value,
    OrderStatus.PAID.value,
    OrderStatus.SHIPPED.value,
    OrderStatus.OVERDUE.value,
}


@dataclass(frozen=True)
class Order:
    """In-memory representation of a row in orders table."""
    order_id: str
    user_name: str
    user_wechat: str
    sku: str
    start_at: datetime
    end_at: datetime
    buffer_hours: int
    status: str
    locker_code: Optional[str]
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class TimeRange:
    start_at: datetime
    end_at: datetime


# @dataclass(frozen=True)
# class Suggestion:
#     """Suggested alternative time slot for a request that conflicts."""
#     start_at: datetime
#     end_at: datetime


# =========
# Exceptions (service layer surfaces clear failure reasons)
# =========

class OrdersServiceError(Exception):
    """Base error for order operations."""


class NotFoundError(OrdersServiceError):
    """Order or SKU not found."""


class ValidationError(OrdersServiceError):
    """Input validation failed (e.g., invalid SKU, end <= start, missing fields)."""


class TerminalOrderError(OrdersServiceError):
    """Attempt to modify a terminal order."""


class ConflictError(OrdersServiceError):
    """
    Raised when a write operation conflicts with existing occupancy.
    Attach conflicts and suggestion if available.
    """
    def __init__(
        self,
        message: str,
        *,
        sku: Optional[str] = None,
        conflicts: Optional[List[str]] = None,
        suggestion: Optional[TimeRange] = None,
    ) -> None:
        super().__init__(message)
        self.sku = sku
        self.conflicts = conflicts or []
        self.suggestion = suggestion


class ConstraintError(OrdersServiceError):
    """DB constraint violation that isn't a time conflict (e.g. shipped requires locker_code)."""
