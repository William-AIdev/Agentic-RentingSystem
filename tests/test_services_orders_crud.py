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
from services.order_types import NotFoundError, OrderStatus, ValidationError

UTC_TZ = UTC
ALLOWED_SKUS = ("black_l", "white_s")


def _new_order_id() -> str:
    return f"TEST_crud_{uuid.uuid4().hex[:8]}"


def _new_sku() -> str:
    return ALLOWED_SKUS[uuid.uuid4().int % 2]


def _naive_to_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC_TZ)
    return dt.astimezone(UTC_TZ)


def _sample_times() -> tuple[datetime, datetime]:
    start = datetime.now(UTC).replace(microsecond=0)
    return start, start + timedelta(hours=2)


def _get_order_in_new_session(order_id: str, engine):
    from sqlalchemy.orm import sessionmaker

    SessionLocal = sessionmaker(
        bind=engine,
        expire_on_commit=False,
        autoflush=False,
        future=True,
    )
    session = SessionLocal()
    try:
        return svc.get_order_detail(order_id, client=session)
    finally:
        session.close()


def test_add_and_get_order_roundtrip(db_session, engine):
    start, end = _sample_times()
    sku = _new_sku()
    order_id = _new_order_id()
    created_order = svc.add_order_to_db(
        order_id=order_id,
        user_name="Alice",
        user_wechat="wx_alice",
        sku=sku,
        start_at=start,
        end_at=end,
    )
    fetched = _get_order_in_new_session(order_id, engine)
    assert created_order.order_id == order_id
    assert fetched.order_id == order_id
    assert fetched.status == OrderStatus.RESERVED.value
    expected_start = _naive_to_utc(start)
    expected_end = _naive_to_utc(end)
    assert fetched.start_at_iso.timestamp() == expected_start.timestamp()
    assert fetched.end_at_iso.timestamp() == expected_end.timestamp()


def test_edit_order_updates_time_and_fields(db_session, engine):
    start, end = _sample_times()
    sku = _new_sku()
    order_id = _new_order_id()
    svc.add_order_to_db(
        order_id=order_id,
        user_name="C",
        user_wechat="wx_c",
        sku=sku,
        start_at=start,
        end_at=end,
    )
    new_start = start + timedelta(days=1)
    new_end = new_start + timedelta(hours=3)
    svc.edit_order_from_db(
        order_id,
        patch={"start_at": new_start, "end_at": new_end, "status": OrderStatus.PAID.value},
    )
    updated = _get_order_in_new_session(order_id, engine)
    assert updated.start_at_iso == _naive_to_utc(new_start)
    assert updated.end_at_iso == _naive_to_utc(new_end)
    assert updated.status == OrderStatus.PAID.value


def test_cancel_soft_and_hard_delete(db_session, engine):
    start, end = _sample_times()
    sku1 = _new_sku()
    order_id1 = _new_order_id()
    svc.add_order_to_db(
        order_id=order_id1,
        user_name="E",
        user_wechat="wx_e",
        sku=sku1,
        start_at=start,
        end_at=end,
    )
    soft = svc.cancel_order(order_id1)
    assert soft.status == OrderStatus.CANCELED.value

    sku2 = _new_sku()
    order_id2 = _new_order_id()
    svc.add_order_to_db(
        order_id=order_id2,
        user_name="F",
        user_wechat="wx_f",
        sku=sku2,
        start_at=start,
        end_at=end,
    )
    deleted = svc.cancel_order(order_id2, hard_delete=True)
    assert deleted.order_id == order_id2
    with pytest.raises(NotFoundError):
        _get_order_in_new_session(order_id2, engine)


def test_mark_paid_and_deliver_and_finish(db_session, engine):
    start, end = _sample_times()
    sku = _new_sku()
    order_id = _new_order_id()
    svc.add_order_to_db(
        order_id=order_id,
        user_name="G",
        user_wechat="wx_g",
        sku=sku,
        start_at=start,
        end_at=end,
    )

    svc.mark_order_paid(order_id)
    paid = _get_order_in_new_session(order_id, engine)
    assert paid.status == OrderStatus.PAID.value

    with pytest.raises(ValidationError):
        svc.deliver_order(order_id, locker_code="")

    svc.deliver_order(order_id, locker_code="LC123")
    shipped = _get_order_in_new_session(order_id, engine)
    assert shipped.status == OrderStatus.SHIPPED.value
    assert shipped.locker_code == "LC123"

    svc.finish_order(order_id)
    finished = _get_order_in_new_session(order_id, engine)
    assert finished.status == OrderStatus.SUCCESSFUL.value
