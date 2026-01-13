import os
from datetime import datetime, timedelta, timezone
from supabase import create_client
from supabase.lib.client_options import ClientOptions
from dotenv import load_dotenv

load_dotenv()

TZ_SYDNEY = timezone(timedelta(hours=11))

OCCUPYING_STATUSES = ["reserved", "paid", "shipped", "overdue"]

def get_client():
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    return create_client(
        url,
        key,
        options=ClientOptions(auto_refresh_token=False, persist_session=False),
    )

def main():
    sb = get_client()
    sku = "BLACK_L"
    now_iso = datetime.now(TZ_SYDNEY).isoformat()

    # occupied 是 tstzrange 列；用 PostgREST 的 range 操作在 SDK 里不总是直观。
    # MVP 最简单：把过滤范围缩小到同 sku + 占用状态，再在 Python 里判断 now 是否在 [start_at, end_at+3h)。
    rows = (
        sb.table("orders")
        .select("order_id, start_at, end_at, buffer_hours, status")
        .eq("sku", sku)
        .in_("status", OCCUPYING_STATUSES)
        .execute()
        .data
    )

    now = datetime.fromisoformat(now_iso)
    print(rows)
    
    for r in rows:
        start = datetime.fromisoformat(r["start_at"])
        end = datetime.fromisoformat(r["end_at"]) + timedelta(hours=int(r["buffer_hours"]))
        if start <= now < end:  # 半开区间
            print(f"❌ {sku} NOT free now. Occupied by {r['order_id']} until {end.isoformat()}")
            return

    print(f"✅ {sku} is free now.")

if __name__ == "__main__":
    main()
