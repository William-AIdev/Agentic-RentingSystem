import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.exc import IntegrityError


def _new_order_id(prefix: str) -> str:
    return f"TEST_db_{prefix}_{uuid.uuid4().hex[:8]}"


def _insert_order(
    *,
    engine,
    order_id: str,
    sku: str,
    start_at: datetime,
    end_at: datetime,
    status: str = "reserved",
    locker_code=None,
    buffer_hours: int = 3,
) -> None:
    with engine.begin() as conn:
        conn.exec_driver_sql(
            """
            INSERT INTO orders (
                order_id,
                user_name,
                user_wechat,
                sku,
                start_at,
                end_at,
                buffer_hours,
                status,
                locker_code
            )
            VALUES (%(order_id)s, %(user_name)s, %(user_wechat)s, %(sku)s, %(start_at)s,
                    %(end_at)s, %(buffer_hours)s, %(status)s, %(locker_code)s)
            """,
            {
                "order_id": order_id,
                "user_name": "DB",
                "user_wechat": "wx_db",
                "sku": sku,
                "start_at": start_at,
                "end_at": end_at,
                "buffer_hours": buffer_hours,
                "status": status,
                "locker_code": locker_code,
            },
        )


def test_db_exclusion_constraint_no_overlap(engine):
    start = datetime.now(UTC).replace(microsecond=0)
    end = start + timedelta(hours=2)
    sku = "BLACK_L"

    _insert_order(
        engine=engine,
        order_id=_new_order_id("ov1"),
        sku=sku,
        start_at=start,
        end_at=end,
    )

    with pytest.raises(IntegrityError):
        _insert_order(
            engine=engine,
            order_id=_new_order_id("ov2"),
            sku=sku,
            start_at=start + timedelta(minutes=30),
            end_at=end + timedelta(minutes=30),
        )


def test_db_locker_code_required_for_shipped(engine):
    start = datetime.now(UTC).replace(microsecond=0)
    end = start + timedelta(hours=2)
    sku = "BLACK_L"

    with pytest.raises(IntegrityError):
        _insert_order(
            engine=engine,
            order_id=_new_order_id("ship"),
            sku=sku,
            start_at=start,
            end_at=end,
            status="shipped",
            locker_code=None,
        )


def test_db_locker_code_required_for_successful(engine):
    start = datetime.now(UTC).replace(microsecond=0)
    end = start + timedelta(hours=2)
    sku = "WHITE_S"

    with pytest.raises(IntegrityError):
        _insert_order(
            engine=engine,
            order_id=_new_order_id("succ"),
            sku=sku,
            start_at=start,
            end_at=end,
            status="successful",
            locker_code=None,
        )
