import os
import uuid
from datetime import datetime, timedelta, timezone
from supabase import create_client
from supabase.lib.client_options import ClientOptions
from dotenv import load_dotenv

load_dotenv()

TZ_SYDNEY = timezone(timedelta(hours=11))

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
    base = datetime.now(TZ_SYDNEY).replace(hour=8, minute=0, second=0, microsecond=0) + timedelta(days=2)

    # 订单 A：08:00-10:00
    order_a = f"O_OV_{uuid.uuid4().hex[:6]}A"
    a = {
        "order_id": order_a,
        "user_name": "A",
        "user_wechat": "wx_a",
        "sku": "WHITE_M",
        "start_at": iso(base),
        "end_at": iso(base.replace(hour=10)),
        "status": "reserved",
    }
    sb.table("orders").insert(a).execute()
    print("✅ Insert A ok:", order_a)

    # 订单 B：10:00-12:00（+buffer hours重叠，应失败）
    order_b = f"O_OV_{uuid.uuid4().hex[:6]}B"
    b = {
        "order_id": order_b,
        "user_name": "B",
        "user_wechat": "wx_b",
        "sku": "WHITE_M",
        "start_at": iso(base.replace(hour=12)),
        "end_at": iso(base.replace(hour=14)),
        "status": "reserved",
    }

    try:
        resp = sb.table("orders").insert(b).execute()
        if getattr(resp, "data", None) is not None:
            print("⚠️ Unexpected: overlap insert succeeded:", resp.data)
        else:
            print("✅ Overlap blocked (resp has no data):", resp)
    except Exception as e:
        print("✅ Overlap blocked (exception):", e)

if __name__ == "__main__":
    main()
