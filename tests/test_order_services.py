from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Tuple
import sys
import uuid

import pytest

from dotenv import load_dotenv

load_dotenv()

# Ensure repo root is importable when running pytest directly.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services import order_services as svc
from services.types import (
    NotFoundError,
    OrderStatus,
    TerminalOrderError,
    ValidationError,
)

UTC_TZ = timezone.utc
ALLOWED_SKUS = ("black_l", "white_s")


@pytest.fixture()
def client_and_cleanup():
    client = svc.create_db_client()
    created: List[str] = []
    yield client, created
    for order_id in created:
        try:
            svc.cancel_order(order_id, client=client, hard_delete=True)
        except Exception:
            pass


def _new_order_id(created: List[str]) -> str:
    order_id = f"TEST_serv_{uuid.uuid4().hex[:8]}"
    created.append(order_id)
    return order_id


def _new_sku() -> str:
    return ALLOWED_SKUS[uuid.uuid4().int % 2]


def _naive_to_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC_TZ)
    return dt.astimezone(UTC_TZ)


def _sample_times() -> Tuple[datetime, datetime]:
    start = datetime.now(timezone.utc).replace(microsecond=0)
    return start, start + timedelta(hours=2)


def test_add_and_get_order_roundtrip(client_and_cleanup):
    client, created_ids = client_and_cleanup
    start, end = _sample_times()
    sku = _new_sku()
    order_id = _new_order_id(created_ids)
    created_order = svc.add_order_to_db(
        order_id=order_id,
        user_name="Alice",
        user_wechat="wx_alice",
        sku=sku,
        start_at=start,
        end_at=end,
        client=client,
    )
    fetched = svc.get_order_detail(order_id, client=client)
    assert created_order.order_id == order_id
    assert fetched.order_id == order_id
    assert fetched.status == OrderStatus.RESERVED.value
    assert fetched.start_at_iso == _naive_to_utc(start)
    assert fetched.end_at_iso == _naive_to_utc(end)


def test_add_order_invalid_time_raises(client_and_cleanup):
    client, created_ids = client_and_cleanup
    start = datetime.now(timezone.utc)
    sku = _new_sku()
    order_id = _new_order_id(created_ids)
    with pytest.raises(ValidationError):
        svc.add_order_to_db(
            order_id=order_id,
            user_name="Bob",
            user_wechat="wx_bob",
            sku=sku,
            start_at=start,
            end_at=start - timedelta(hours=1),
            client=client,
        )


def test_edit_order_updates_time_and_fields(client_and_cleanup):
    client, created_ids = client_and_cleanup
    start, end = _sample_times()
    sku = _new_sku()
    order_id = _new_order_id(created_ids)
    svc.add_order_to_db(
        order_id=order_id,
        user_name="C",
        user_wechat="wx_c",
        sku=sku,
        start_at=start,
        end_at=end,
        client=client,
    )
    new_start = start + timedelta(days=1)
    new_end = new_start + timedelta(hours=3)
    updated = svc.edit_order_from_db(
        order_id,
        patch={"start_at": new_start, "end_at": new_end, "status": OrderStatus.PAID.value},
        client=client,
    )
    assert updated.start_at_iso == _naive_to_utc(new_start)
    assert updated.end_at_iso == _naive_to_utc(new_end)
    assert updated.status == OrderStatus.PAID.value


def test_terminal_order_rejects_edits(client_and_cleanup):
    client, created_ids = client_and_cleanup
    start, end = _sample_times()
    sku = _new_sku()
    order_id = _new_order_id(created_ids)
    svc.add_order_to_db(
        order_id=order_id,
        user_name="D",
        user_wechat="wx_d",
        sku=sku,
        start_at=start,
        end_at=end,
        client=client,
    )
    svc.finish_order(order_id, client=client)
    with pytest.raises(TerminalOrderError):
        svc.edit_order_from_db(order_id, patch={"status": OrderStatus.PAID.value}, client=client)


def test_cancel_soft_and_hard_delete(client_and_cleanup):
    client, created_ids = client_and_cleanup
    start, end = _sample_times()
    sku1 = _new_sku()
    order_id1 = _new_order_id(created_ids)
    svc.add_order_to_db(
        order_id=order_id1,
        user_name="E",
        user_wechat="wx_e",
        sku=sku1,
        start_at=start,
        end_at=end,
        client=client,
    )
    soft = svc.cancel_order(order_id1, client=client)
    assert soft.status == OrderStatus.CANCELED.value

    sku2 = _new_sku()
    order_id2 = _new_order_id(created_ids)
    svc.add_order_to_db(
        order_id=order_id2,
        user_name="F",
        user_wechat="wx_f",
        sku=sku2,
        start_at=start,
        end_at=end,
        client=client,
    )
    deleted = svc.cancel_order(order_id2, client=client, hard_delete=True)
    assert deleted.order_id == order_id2
    with pytest.raises(NotFoundError):
        svc.get_order_detail(order_id2, client=client)


def test_mark_paid_and_deliver_and_finish(client_and_cleanup):
    client, created_ids = client_and_cleanup
    start, end = _sample_times()
    sku = _new_sku()
    order_id = _new_order_id(created_ids)
    svc.add_order_to_db(
        order_id=order_id,
        user_name="G",
        user_wechat="wx_g",
        sku=sku,
        start_at=start,
        end_at=end,
        client=client,
    )

    paid = svc.mark_order_paid(order_id, client=client)
    assert paid.status == OrderStatus.PAID.value

    with pytest.raises(ValidationError):
        svc.deliver_order(order_id, locker_code="", client=client)

    shipped = svc.deliver_order(order_id, locker_code="LC123", client=client)
    assert shipped.status == OrderStatus.SHIPPED.value
    assert shipped.locker_code == "LC123"

    finished = svc.finish_order(order_id, client=client)
    assert finished.status == OrderStatus.SUCCESSFUL.value


def test_suggest_time_slots_text(client_and_cleanup):
    client, created_ids = client_and_cleanup
    sku = "white_s"
    window_days = 5

    base_now = datetime.now(timezone.utc).replace(microsecond=0)

    # Expected rental time: 2 hours after now, for 3 hours.
    expected_start = base_now + timedelta(hours=2)
    expected_end = expected_start + timedelta(hours=3)

    # Create two reservations that, with default 3h buffer so only 1 hour available between
    res_expected_start = expected_start + timedelta(hours=1)
    res_expected_end = res_expected_start + timedelta(hours=4)
    res_expected_start_2 = res_expected_end + timedelta(hours=4)
    res_expected_end_2 = res_expected_start_2 + timedelta(hours=2)

    svc.add_order_to_db(
        order_id=_new_order_id(created_ids),
        user_name="A",
        user_wechat="wx_a",
        sku=sku,
        start_at=res_expected_start,
        end_at=res_expected_end,
        client=client,
    )

    svc.add_order_to_db(
        order_id=_new_order_id(created_ids),
        user_name="B",
        user_wechat="wx_b",
        sku=sku,
        start_at=res_expected_start_2,
        end_at=res_expected_end_2,
        client=client,
    )

    # Ask for suggestions around the expected window.
    suggest_text = svc.suggest_time_slots_text(
        sku=sku,
        expected_start_at=expected_start,
        expected_end_at=expected_end,
        client=client,
        window_days=window_days,
    )

    # Window is expected_start - X days to expected_end + X days.
    window_start = (expected_start - timedelta(days=window_days)).isoformat()
    window_end = (expected_end + timedelta(days=window_days)).isoformat()
    # Two reservations + buffer merge into a single blocked span at the window's start.
    block_start = (res_expected_start - timedelta(hours=svc.DEFAULT_BUFFER_HOURS)).isoformat()
    block_end = (res_expected_end_2 + timedelta(hours=svc.DEFAULT_BUFFER_HOURS)).isoformat()

    # Only slots long enough to cover the 6-day duration should be listed.
    assert f"{block_end} 到 {window_end}" in suggest_text
    assert f"{window_start} 到 {block_start}" not in suggest_text
