import os
from supabase import create_client
from supabase.lib.client_options import ClientOptions
from dotenv import load_dotenv

load_dotenv()

def get_client():
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    # server-side recommended options (no session persistence)
    return create_client(
        url,
        key,
        options=ClientOptions(auto_refresh_token=False, persist_session=False),
    )

def main():
    sb = get_client()

    # 1) 简单 select：读 orders 表前 3 条
    resp = sb.table("orders").select("*").limit(3).execute()
    if getattr(resp, "data", None) is None:
        raise RuntimeError(f"Select failed: {resp}")

    print("✅ Connected. Sample rows:")
    for row in resp.data:
        print(row)

if __name__ == "__main__":
    main()

    
