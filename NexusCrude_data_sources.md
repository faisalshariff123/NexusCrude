# NexusCrude Data Sources

## Purpose

This document defines the initial source universe for NexusCrude. The goal is to prioritize sources that are public, reputable, and structurally useful for data extraction and analyst workflows.

## Tier 1 Sources

These should be ingested first.

### EIA

Use for:

- Country analysis briefs
- Iraq production/export context
- Infrastructure summaries
- Energy sector overviews

Key link:
- https://www.eia.gov/international/analysis/country/IRQ

### OPEC

Use for:

- Monthly Oil Market Reports
- Market context
- Supply and production commentary
- Wider regional production positioning

Key link:
- https://publications.opec.org/momr

### EITI Iraq

Use for:

- Transparency reports
- Revenue and disclosure context
- Institutional and reporting detail

Key links:
- https://eiti.org/countries/iraq
- https://eiti.org/sites/default/files/2024-01/Iraq%202021%20EITI%20Report.pdf

### IEA

Use for:

- Sector outlooks
- Strategic energy context
- Longer-form system analysis

Key link:
- https://iea.blob.core.windows.net/assets/fb1f67b9-3515-4b5a-bb40-06ca0b83ef70/Iraq_Energy_Outlook.pdf

## Tier 2 Sources

These are important after the first pipeline works.

### Iraqi Ministry of Oil

Use for:

- Official ministry announcements
- Field/project updates
- Production and export commentary

Reference link:
- http://www.oil.gov.iq/

### SOMO-related reporting

Use for:

- Export volumes
- Revenue snapshots
- Monthly shipment narratives

Note: official accessibility may vary, so regional reporting may be needed as a bridge.

### Reputable regional news sources

Use for:

- Fresh market updates
- Export disruptions
- Infrastructure incidents
- Political developments affecting energy flows

Examples:
- Shafaq News
- Reuters
- Financial Times
- other reputable English-language regional coverage

## Data Types to Extract

Normalize around these entities first:

- Production figures
- Export figures
- Revenue figures
- Reserve figures
- Infrastructure assets and locations
- Company/project references
- Time periods
- Geographic routing or destination context
- Geopolitical disruptions

## Extraction Rules

- Always preserve source URL or source document reference.
- Preserve original wording in notes when context matters.
- Distinguish between annual, monthly, daily, and estimated figures.
- Keep units explicit.
- Flag uncertain or conflicting values for analyst review.

## Initial Schema Thinking

Core table candidates:

- `production_data`
- `sources`
- `events`
- `assets`
- `companies`
- `reports`

## Ingestion Priority Order

1. EIA Iraq PDFs
2. OPEC monthly reports
3. Iraq EITI reports
4. IEA Iraq outlook material
5. Ministry releases and current news feeds
