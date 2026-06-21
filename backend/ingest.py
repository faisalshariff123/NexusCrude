"""
NexusCrude — ingest.py
Secure, production-grade ingestion pipeline for public oil intelligence PDFs.

Security measures implemented:
  - Env var presence validated at startup (fail fast, no partial init)
  - No secrets ever printed or logged
  - Allowlist for permitted source URLs (no arbitrary URL injection)
  - PDF size capped at MAX_PDF_BYTES before reading into memory
  - HTTP request timeouts enforced (connect + read)
  - LLM output field-level sanitization before any DB write
  - All text fields truncated to safe lengths before insert
  - NUMERIC coercion with range guard (no absurd values go in)
  - Supabase upsert only — never raw SQL, no injection surface
  - Ingestion log always written, even on crash (finally block)
  - No stack traces exposed in log output (error_detail is controlled)
  - Requests uses verify=True (TLS cert validation) by default
"""

import hashlib
import io
import json
import logging
import os
import re
import sys
from datetime import date
from typing import Optional

import pdfplumber
import requests
from dotenv import load_dotenv
from openai import OpenAI
from supabase import create_client, Client

# ─────────────────────────────────────────────────────────────
# LOGGING — structured, no secrets ever
# ─────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%SZ",
)
log = logging.getLogger("nexuscrude.ingest")

# ─────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────
MAX_PDF_BYTES      = 50 * 1024 * 1024
HTTP_TIMEOUT       = (10, 60)
MAX_TEXT_FIELD     = 2000
MAX_VALUE_TEXT     = 100
MAX_NUMERIC_VALUE  = 1_000_000_000
MIN_NUMERIC_VALUE  = -1_000_000_000
MODEL              = "google/gemini-2.0-flash-001"

ALLOWED_SOURCE_URLS: dict[str, dict] = {
    "https://www.eia.gov/international/content/analysis/countries_long/Iraq/Iraq_2025.pdf": {
        "source_name":    "EIA Iraq 2025",
        "document_title": "Iraq — Energy Sector Overview 2025",
        "published_at":   date(2025, 1, 1),
        "source_type":    "pdf",
        "notes":          "EIA country analysis brief for Iraq, 2025 edition",
    },
}

UNIT_MAP: dict[str, str] = {
    "million barrels per day": "mb/d",
    "million b/d":             "mb/d",
    "mbd":                     "mb/d",
    "mbpd":                    "mb/d",
    "thousand barrels per day":"kb/d",
    "thousand b/d":            "kb/d",
    "tbpd":                    "kb/d",
    "barrels per day":         "b/d",
    "bpd":                     "b/d",
    "usd billion":             "USD billion",
    "billion dollars":         "USD billion",
    "billion usd":             "USD billion",
    "usd million":             "USD million",
    "million dollars":         "USD million",
    "million usd":             "USD million",
    "percent":                 "%",
    "per cent":                "%",
}

METRIC_MAP: dict[str, str] = {
    "total crude oil production":  "crude oil production",
    "crude production":            "crude oil production",
    "oil production":              "crude oil production",
    "total production":            "crude oil production",
    "crude oil exports":           "crude oil exports",
    "total crude exports":         "crude oil exports",
    "oil exports":                 "crude oil exports",
    "export revenues":             "oil export revenue",
    "oil revenues":                "oil export revenue",
    "crude export revenue":        "oil export revenue",
    "oil revenue":                 "oil export revenue",
    "petroleum revenue":           "oil export revenue",
}

VALID_PERIOD_TYPES  = {"annual", "monthly", "daily", "quarterly", "estimated", "unknown"}
VALID_CONFIDENCE    = {"high", "medium", "low", "uncertain"}

EXTRACTION_PROMPT = """You are a precise data extractor for Iraq oil intelligence.

Extract ALL Iraq crude oil production, export, and revenue data points from the text.
For each data point include the exact page number it came from.

Return ONLY valid JSON in this exact format — no markdown, no prose:
{
  "data": [
    {
      "metric": "crude oil production",
      "value": "4.2",
      "unit": "mb/d",
      "period_type": "annual",
      "period_year": 2024,
      "period_month": null,
      "geography": "Iraq",
      "source_page": 3,
      "original_text": "Iraq produced 4.2 mb/d of crude oil in 2024",
      "confidence": "high",
      "notes": "annual average figure"
    }
  ]
}

Hard rules:
- value must be a plain numeric string, no commas, no units, no ranges
- period_month is integer 1-12 or null
- period_year is 4-digit integer or null
- Do not invent or estimate data — only extract what is explicitly stated
- If a figure is approximate or projected, set confidence to "low" or "uncertain"
- original_text must be a verbatim short quote from the source, max 300 chars
"""

def validate_env() -> None:
    required = ["SUPABASE_URL", "SUPABASE_SERVICE_KEY", "OPENROUTER_API_KEY"]
    missing  = [k for k in required if not os.getenv(k)]
    if missing:
        log.error("Missing required environment variables: %s", missing)
        sys.exit(1)
    log.info("Environment validated ✓")

def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def truncate(val: Optional[str], max_len: int) -> Optional[str]:
    if val is None:
        return None
    s = str(val).strip()
    return s[:max_len] if len(s) > max_len else s

def normalize_unit(raw: str) -> str:
    return UNIT_MAP.get(raw.strip().lower(), truncate(raw, 50))

def normalize_metric(raw: str) -> str:
    key = raw.strip().lower()
    return METRIC_MAP.get(key, truncate(key, 200))

def coerce_numeric(val_str) -> Optional[float]:
    try:
        clean = re.sub(r"[,\s]", "", str(val_str))
        if not re.match(r"^-?\d+(\.\d+)?$", clean):
            return None
        result = float(clean)
        if not (MIN_NUMERIC_VALUE <= result <= MAX_NUMERIC_VALUE):
            log.warning("Numeric value out of range, storing NULL: %s", clean)
            return None
        return result
    except (ValueError, TypeError):
        return None

def safe_int(val, min_val: int = None, max_val: int = None) -> Optional[int]:
    try:
        i = int(val)
        if min_val is not None and i < min_val:
            return None
        if max_val is not None and i > max_val:
            return None
        return i
    except (ValueError, TypeError):
        return None

def validate_row(row: dict) -> list[str]:
    errors = []
    if not row.get("metric") or not str(row["metric"]).strip():
        errors.append("missing metric")
    raw_val = row.get("value")
    if raw_val is None or str(raw_val).strip() == "":
        errors.append("missing value")
    if not row.get("unit") or not str(row["unit"]).strip():
        errors.append("missing unit")
    period_type = row.get("period_type", "")
    if period_type not in VALID_PERIOD_TYPES:
        errors.append(f"invalid period_type: {period_type!r}")
    return errors

def sanitize_row(row: dict, source_id: str) -> dict:
    raw_value = row.get("value")
    period_type = row.get("period_type", "unknown")
    if period_type not in VALID_PERIOD_TYPES:
        period_type = "unknown"

    confidence = row.get("confidence", "medium")
    if confidence not in VALID_CONFIDENCE:
        confidence = "medium"

    return {
        "metric":        normalize_metric(row.get("metric", "")),
        "value":         coerce_numeric(raw_value),
        "value_text":    truncate(str(raw_value), MAX_VALUE_TEXT),
        "unit":          normalize_unit(row.get("unit", "")),
        "period_type":   period_type,
        "period_year":   safe_int(row.get("period_year"), min_val=1900, max_val=2100),
        "period_month":  safe_int(row.get("period_month"), min_val=1, max_val=12),
        "geography":     truncate(row.get("geography", "Iraq"), 200),
        "source_id":     source_id,
        "source_page":   safe_int(row.get("source_page"), min_val=1, max_val=9999),
        "original_text": truncate(row.get("original_text"), MAX_TEXT_FIELD),
        "confidence":    confidence,
        "notes":         truncate(row.get("notes"), MAX_TEXT_FIELD),
    }

def run(pdf_url: str) -> None:
    if pdf_url not in ALLOWED_SOURCE_URLS:
        log.error("URL not in allowlist: %s", pdf_url)
        sys.exit(1)
    meta = ALLOWED_SOURCE_URLS[pdf_url]

    load_dotenv()
    validate_env()

    supabase: Client = create_client(
        os.getenv("SUPABASE_URL"),
        os.getenv("SUPABASE_SERVICE_KEY"),
    )
    llm_client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=os.getenv("OPENROUTER_API_KEY"),
    )

    source_id        = None
    rows_extracted   = 0
    rows_inserted    = 0
    rows_skipped     = 0
    rows_failed      = 0
    run_status       = "failed"
    error_detail     = None

    try:
        log.info("Fetching PDF: %s", pdf_url)
        resp = requests.get(pdf_url, timeout=HTTP_TIMEOUT, stream=True)
        resp.raise_for_status()

        chunks = []
        total  = 0
        for chunk in resp.iter_content(chunk_size=65536):
            total += len(chunk)
            if total > MAX_PDF_BYTES:
                raise ValueError(f"PDF exceeds size limit of {MAX_PDF_BYTES // (1024*1024)} MB")
            chunks.append(chunk)
        pdf_bytes = b"".join(chunks)
        file_hash = sha256_hex(pdf_bytes)
        log.info("PDF fetched — %d bytes, SHA-256: %s...", len(pdf_bytes), file_hash[:16])

        log.info("Upserting sources record")
        source_payload = {
            "source_name":    meta["source_name"],
            "source_url":     pdf_url,
            "document_title": meta["document_title"],
            "published_at":   str(meta["published_at"]),
            "source_type":    meta["source_type"],
            "file_hash":      file_hash,
            "notes":          meta["notes"],
        }
        src_res = supabase.table("sources").upsert(
            source_payload, on_conflict="source_url,file_hash"
        ).execute()
        source_id = src_res.data[0]["id"]
        log.info("source_id: %s", source_id)

        log.info("Extracting text by page")
        pages_text = []
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for i, page in enumerate(pdf.pages, start=1):
                text = page.extract_text() or ""
                if text.strip():
                    pages_text.append({"page": i, "text": text})

        full_text = "\n".join(f"[PAGE {p['page']}]\n{p['text']}" for p in pages_text)
        log.info("%d pages with extractable text", len(pages_text))

        log.info("Running LLM extraction (model: %s)", MODEL)
        response = llm_client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": EXTRACTION_PROMPT + "\n\n" + full_text}],
            response_format={"type": "json_object"},
        )
        raw_content = response.choices[0].message.content
        clean_content = re.sub(r'^```json\s*|```$', '', raw_content.strip(), flags=re.MULTILINE).strip()

        try:
            results = json.loads(clean_content)
        except json.JSONDecodeError as exc:
            error_detail = f"JSON decode error at char {exc.pos}"
            raise RuntimeError("LLM returned invalid JSON") from exc

        candidates = results.get("data", [])
        rows_extracted = len(candidates)
        log.info("LLM returned %d candidate rows", rows_extracted)

        for raw_row in candidates:
            if not isinstance(raw_row, dict):
                rows_failed += 1
                continue

            validation_errors = validate_row(raw_row)
            if validation_errors:
                log.warning("Row skipped (validation): %s | metric=%s",
                            validation_errors, raw_row.get("metric", "?"))
                rows_failed += 1
                continue

            clean_row = sanitize_row(raw_row, source_id)

            try:
                supabase.table("production_data").upsert(
                    clean_row,
                    on_conflict="source_id,metric,period_type,period_year,period_month,unit,value_text",
                ).execute()
                rows_inserted += 1
            except Exception as exc:
                log.error("Upsert failed (%s) for metric: %s",
                          type(exc).__name__, clean_row.get("metric", "?"))
                rows_failed += 1

        run_status = "success" if rows_failed == 0 else "partial"

    except Exception as exc:
        run_status = "failed"
        error_detail = error_detail or type(exc).__name__
        log.error("Pipeline error: %s", type(exc).__name__)
        raise

    finally:
        if source_id or run_status == "failed":
            try:
                supabase.table("ingestion_log").insert({
                    "source_id":      source_id,
                    "status":         run_status,
                    "rows_extracted": rows_extracted,
                    "rows_inserted":  rows_inserted,
                    "rows_skipped":   rows_skipped,
                    "rows_failed":    rows_failed,
                    "error_detail":   error_detail,
                    "model_used":     MODEL,
                }).execute()
                log.info(
                    "Run logged — status=%s extracted=%d inserted=%d skipped=%d failed=%d",
                    run_status, rows_extracted, rows_inserted, rows_skipped, rows_failed
                )
            except Exception as log_exc:
                log.error("Failed to write ingestion_log: %s", type(log_exc).__name__)

if __name__ == "__main__":
    target_url = (
        sys.argv[1]
        if len(sys.argv) > 1
        else "https://www.eia.gov/international/content/analysis/countries_long/Iraq/Iraq_2025.pdf"
    )
    run(target_url)