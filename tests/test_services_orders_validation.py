import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from dotenv import load_dotenv

load_dotenv()

# Ensure repo root is importable when running pytest directly.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services import order_services as svc
from services.order_types import ConflictError, OrderStatus, TerminalOrderError, ValidationError

ALLOWED_SKUS = ("black_l", "white_s")


def _new_order_id() -> str:
    return f"TEST_val_{uuid.uuid4().hex[:8]}"


def _new_sku() -> str:
    return ALLOWED_SKUS[uuid.uuid4().int % 2]


def _sample_times() -> tuple[datetime, datetime]:
    start = datetime.now(UTC).replace(microsecond=0)
    return start, start + timedelta(hours=2)


def test_add_order_invalid_time_raises(db_session):
    start = datetime.now(UTC)
    sku = _new_sku()
    order_id = _new_order_id()
    with pytest.raises(ValidationError):
        svc.add_order_to_db(
            order_id=order_id,
            user_name="Bob",
            user_wechat="wx_bob",
            sku=sku,
            start_at=start,
            end_at=start - timedelta(hours=1),
        )


def test_add_order_duplicate_id_conflict(db_session):
    start, end = _sample_times()
    sku = _new_sku()
    order_id = _new_order_id()
    svc.add_order_to_db(
        order_id=order_id,
        user_name="Dup",
        user_wechat="wx_dup",
        sku=sku,
        start_at=start,
        end_at=end,
    )
    with pytest.raises(ConflictError):
        svc.add_order_to_db(
            order_id=order_id,
            user_name="Dup2",
            user_wechat="wx_dup2",
            sku=sku,
            start_at=start + timedelta(hours=4),
            end_at=end + timedelta(hours=4),
        )


def test_add_order_overlap_conflict(db_session):
    start, end = _sample_times()
    sku = _new_sku()
    svc.add_order_to_db(
        order_id=_new_order_id(),
        user_name="O1",
        user_wechat="wx_o1",
        sku=sku,
        start_at=start,
        end_at=end,
    )
    with pytest.raises(ConflictError):
        svc.add_order_to_db(
            order_id=_new_order_id(),
            user_name="O2",
            user_wechat="wx_o2",
            sku=sku,
            start_at=start + timedelta(minutes=30),
            end_at=end + timedelta(minutes=30),
        )


def test_edit_order_empty_patch_raises(db_session):
    start, end = _sample_times()
    order_id = _new_order_id()
    svc.add_order_to_db(
        order_id=order_id,
        user_name="Patch",
        user_wechat="wx_patch",
        sku=_new_sku(),
        start_at=start,
        end_at=end,
    )
    with pytest.raises(ValidationError):
        svc.edit_order_from_db(order_id, patch={})


def test_terminal_order_rejects_edits(db_session):
    start, end = _sample_times()
    sku = _new_sku()
    order_id = _new_order_id()
    svc.add_order_to_db(
        order_id=order_id,
        user_name="D",
        user_wechat="wx_d",
        sku=sku,
        start_at=start,
        end_at=end,
    )
    svc.finish_order(order_id)
    with pytest.raises(TerminalOrderError):
        svc.edit_order_from_db(order_id, patch={"status": OrderStatus.PAID.value})


def test_update_order_overlap_conflict(db_session):
    start, end = _sample_times()
    sku = _new_sku()
    order_id_1 = _new_order_id()
    order_id_2 = _new_order_id()

    safe_gap = timedelta(hours=svc.DEFAULT_BUFFER_HOURS + 1)

    svc.add_order_to_db(
        order_id=order_id_1,
        user_name="A",
        user_wechat="wx_a",
        sku=sku,
        start_at=start,
        end_at=end,
    )
    svc.add_order_to_db(
        order_id=order_id_2,
        user_name="B",
        user_wechat="wx_b",
        sku=sku,
        start_at=end + safe_gap,
        end_at=end + safe_gap + timedelta(hours=2),
    )

    with pytest.raises(ConflictError):
        svc.edit_order_from_db(
            order_id_2,
            patch={"start_at": start + timedelta(minutes=30), "end_at": end + timedelta(hours=1)},
        )
