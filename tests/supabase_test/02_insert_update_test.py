import os
import uuid
from datetime import datetime, timedelta, timezone
from supabase import create_client
from supabase.lib.client_options import ClientOptions
from dotenv import load_dotenv

load_dotenv()

TZ_SYDNEY = timezone(timedelta(hours=11))  # 你现在是夏令时 +11（悉尼）。如需更严谨可改用 zoneinfo。

def get_client():
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    return create_client(
        url,
        key,
        options=ClientOptions(auto_refresh_token=False, persist_session=False),
    )

def iso(dt: datetime) -> str:
    return dt.isoformat()

def main():
    sb = get_client()

    order_id = f"O_TEST_{uuid.uuid4().hex[:8]}"
    now = datetime.now(TZ_SYDNEY)

    start_at = now.replace(hour=8, minute=0, second=0, microsecond=0) + timedelta(days=1)
    end_at = now.replace(hour=20, minute=0, second=0, microsecond=0) + timedelta(days=1)

    # 1) insert 一条 reserved
    payload = {
        "order_id": order_id,
        "user_name": "Alice",
        "user_wechat": "wx_alice",
        "sku": "BLACK_L",
        "start_at": iso(start_at),
        "end_at": iso(end_at),
        "status": "reserved",
    }
    ins = sb.table("orders").insert(payload).execute()
    print("✅ Insert reserved:", ins.data)

    # 2) update -> shipped 但不带 locker_code（应失败）
    try:
        upd = sb.table("orders").update({"status": "shipped"}).eq("order_id", order_id).execute()
        # 有些 SDK 会把错误放在 resp 里，而不是抛异常
        if getattr(upd, "data", None) is not None:
            print("⚠️ Unexpected: shipped without locker_code succeeded:", upd.data)
        else:
            print("✅ shipped without locker_code blocked (resp has no data):", upd)
    except Exception as e:
        print("✅ shipped without locker_code blocked (exception):", e)

    # 3) update -> shipped + locker_code（应成功）
    upd2 = sb.table("orders").update({"status": "shipped", "locker_code": "111111"}).eq("order_id", order_id).execute()
    print("✅ Update shipped with locker_code:", upd2.data)

if __name__ == "__main__":
    main()
