import os
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()  # MUST be first

url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_KEY")

supabase: Client = create_client(url, key)

# test — insert one dummy row
test_row = {
    "metric": "test connection",
    "value": "1",
    "unit": "test",
    "year": "2026",
    "notes": "testing supabase connection",
    "source": "test"
}

result = supabase.table("production_data").insert(test_row).execute()
print("✓ connection works, inserted:", result.data)