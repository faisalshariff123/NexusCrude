import pdfplumber
import requests
import json
import os
import io
import re
from openai import OpenAI
from dotenv import load_dotenv
from supabase import create_client, Client
load_dotenv()

url: str = os.getenv("SUPABASE_URL")
service_key: str = os.getenv("SUPABASE_SERVICE_KEY")
supabase: Client = create_client(url, service_key)

test_row = {
    "metric": "test connection",
    "value": "1",
    "unit": "test",
    "year": "2026",
    "notes": "testing supabase connection",
    "source": "test"
}

result = supabase.table("production_data").select("*").execute()
print("✓ connection works, inserted:", result.data)


client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY"),
)

pdf_url = "https://www.eia.gov/international/content/analysis/countries_long/Iraq/Iraq_2025.pdf"
pdf_bytes = requests.get(pdf_url).content

with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
    text = "\n".join([p.extract_text() or "" for p in pdf.pages])

prompt = """
You are an expert on extracting info about Iraq crude oil production and export data.
Extract all Iraq crude oil production and export data.
Return ONLY valid JSON in the following exact format:
{
  "data": [
    {"metric": "...", "value": "...", "unit": "...", "year": "...", "notes": "..."}
  ]
}
"""

response = client.chat.completions.create(
    model="google/gemini-2.0-flash-001",
    messages=[
        {"role": "user", "content": prompt + "\n\n" + text}
    ],
    response_format={"type": "json_object"} 
)

raw_content = response.choices[0].message.content


# Sanitize the output: strip markdown backticks and "json" label if they exist
clean_content = re.sub(r'^```json\s*|```$', '', raw_content.strip(), flags=re.MULTILINE).strip()

try:
    results = json.loads(clean_content)
    print("--- PARSED JSON ---")
    print(json.dumps(results, indent=2))
except json.JSONDecodeError as e:
    print(f"Failed to parse JSON. Error: {e}")