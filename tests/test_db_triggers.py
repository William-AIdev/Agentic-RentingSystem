import uuid
from datetime import UTC, datetime, timedelta


def _new_order_id(prefix: str) -> str:
    return f"TEST_trg_{prefix}_{uuid.uuid4().hex[:8]}"


def test_db_trigger_sets_occupied_and_updated_at(engine):
    start = datetime.now(UTC).replace(microsecond=0)
    end = start + timedelta(hours=4)
    buffer_hours = 2
    order_id = _new_order_id("occ")

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
                "user_name": "TR",
                "user_wechat": "wx_tr",
                "sku": "BLACK_L",
                "start_at": start,
                "end_at": end,
                "buffer_hours": buffer_hours,
                "status": "reserved",
                "locker_code": "",
            },
        )

    with engine.begin() as conn:
        row = (
            conn.exec_driver_sql(
                """
            SELECT
                lower(occupied) AS occ_start,
                upper(occupied) AS occ_end,
                created_at,
                updated_at
            FROM orders
            WHERE order_id = %(order_id)s
            """,
                {"order_id": order_id},
            )
            .mappings()
            .one()
        )

    expected_occ_start = start
    expected_occ_end = end + timedelta(hours=buffer_hours)
    assert row["occ_start"] == expected_occ_start
    assert row["occ_end"] == expected_occ_end
    assert row["updated_at"] >= row["created_at"]

    new_start = start + timedelta(days=1)
    new_end = new_start + (end - start)
    past_stamp = datetime(2000, 1, 1, tzinfo=UTC)

    with engine.begin() as conn:
        conn.exec_driver_sql(
            """
            UPDATE orders
            SET start_at = %(start_at)s, end_at = %(end_at)s, updated_at = %(updated_at)s
            WHERE order_id = %(order_id)s
            """,
            {
                "start_at": new_start,
                "end_at": new_end,
                "updated_at": past_stamp,
                "order_id": order_id,
            },
        )

    with engine.begin() as conn:
        row_after = (
            conn.exec_driver_sql(
                """
            SELECT
                lower(occupied) AS occ_start,
                upper(occupied) AS occ_end,
                updated_at
            FROM orders
            WHERE order_id = %(order_id)s
            """,
                {"order_id": order_id},
            )
            .mappings()
            .one()
        )

    assert row_after["occ_start"] == new_start
    assert row_after["occ_end"] == new_end + timedelta(hours=buffer_hours)
    assert row_after["updated_at"] != past_stamp
