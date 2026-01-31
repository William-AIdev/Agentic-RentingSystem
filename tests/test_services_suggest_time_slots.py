import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Ensure repo root is importable when running pytest directly.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services import order_services as svc


def _new_order_id() -> str:
    return f"TEST_slot_{uuid.uuid4().hex[:8]}"


def test_suggest_time_slots_text(db_session):
    sku = "white_s"
    window_days = 5

    base_now = datetime.now(UTC).replace(microsecond=0)

    # Expected rental time: 2 hours after now, for 3 hours.
    expected_start = base_now + timedelta(hours=2)
    expected_end = expected_start + timedelta(hours=3)

    # Create two reservations that, with default 3h buffer so only 1 hour available between
    res_expected_start = expected_start + timedelta(hours=1)
    res_expected_end = res_expected_start + timedelta(hours=4)
    res_expected_start_2 = res_expected_end + timedelta(hours=4)
    res_expected_end_2 = res_expected_start_2 + timedelta(hours=2)

    svc.add_order_to_db(
        order_id=_new_order_id(),
        user_name="A",
        user_wechat="wx_a",
        sku=sku,
        start_at=res_expected_start,
        end_at=res_expected_end,
    )

    svc.add_order_to_db(
        order_id=_new_order_id(),
        user_name="B",
        user_wechat="wx_b",
        sku=sku,
        start_at=res_expected_start_2,
        end_at=res_expected_end_2,
    )

    # Ask for suggestions around the expected window.
    suggest_text = svc.suggest_time_slots_text(
        sku=sku,
        expected_start_at=expected_start,
        expected_end_at=expected_end,
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
