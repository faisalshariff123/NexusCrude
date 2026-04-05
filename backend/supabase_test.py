import os
from pathlib import Path
from dotenv import load_dotenv
from supabase import create_client, Client

ENV_PATH = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=ENV_PATH, override=True)

url = os.getenv("SUPABASE_URL")
service_key = os.getenv("SUPABASE_SERVICE_KEY")

print("Using env file:", ENV_PATH)
print("SUPABASE_URL loaded:", bool(url))
print("SUPABASE_SERVICE_KEY loaded:", bool(service_key))

if not url:
    raise ValueError("Missing SUPABASE_URL")
if not service_key:
    raise ValueError("Missing SUPABASE_SERVICE_KEY")

supabase: Client = create_client(url, service_key)

result = supabase.table("production_data").select("*").limit(5).execute()
print("✓ connection works:", result.data)