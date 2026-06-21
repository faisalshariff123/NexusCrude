# NexusCrude MVP Architecture

## Goal

Build a working MVP that can ingest Iraq oil documents, extract structured facts, store them, and answer source-grounded user questions through a simple web app.

## High-Level Architecture

### 1. Ingestion Layer

Responsibilities:

- Download PDFs or source documents
- Extract raw text
- Chunk or segment long documents
- Send text to an LLM extraction pipeline
- Parse structured JSON output
- Insert normalized rows into the database

Suggested tools:

- Python
- `requests`
- `pdfplumber`
- optional OCR for scanned PDFs later
- Gemini or another extraction model

### 2. Storage Layer

Current choice:

- Supabase PostgreSQL

Current table:

- `production_data`

Recommended expansion:

- `sources`
- `production_data`
- `events`
- `reports`
- `query_logs`

## Example core table direction

### `sources`

- `id`
- `source_name`
- `source_url`
- `document_title`
- `published_at`
- `source_type`
- `ingested_at`

### `production_data`

- `id`
- `metric`
- `value`
- `unit`
- `year`
- `notes`
- `source`
- `created_at`

### `events`

- `id`
- `event_type`
- `title`
- `description`
- `event_date`
- `country`
- `impact_level`
- `source_id`

## 3. Backend API

Suggested first backend:

- Flask or FastAPI

Core endpoints:

- `POST /ingest`
- `GET /metrics`
- `GET /sources`
- `POST /chat`
- `GET /health`

## 4. AI Query Layer

The chat system should not behave like open web search. It should answer from internal sources first and cite the underlying documents or rows.

Basic flow:

1. Receive user question
2. Search structured tables and optionally embeddings
3. Retrieve relevant rows/snippets
4. Build context packet
5. Ask model to answer only from provided context
6. Return answer plus source references

## 5. Frontend

The first frontend can be simple.

Pages:

- Login
- Dashboard
- Source library
- Metrics explorer
- AI query page

## 6. Security

Current best practice for the MVP:

- Keep Supabase RLS enabled
- Use service role key only on backend
- Never expose service role key to frontend
- Add auth before multi-user rollout
- Log ingestion and query activity

## 7. Observability

From the start, track:

- Ingestion success/failure
- JSON parse failures
- Document processing time
- Query latency
- Most-used prompts/questions
- Missing-data requests

## 8. Build Sequence

1. Stabilize ingestion from EIA PDF
2. Expand to OPEC and EITI
3. Normalize schema
4. Add query API
5. Build simple UI
6. Add auth and user accounts
7. Add billing and plans
8. Add alerts and saved searches

## Technical Principle

The MVP should optimize for reliability and explainability, not fancy UI. If the system cannot ingest consistently and answer with grounded evidence, nothing else matters.
