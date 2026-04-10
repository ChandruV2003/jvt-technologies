# Lead Pipeline

This area is the local-first lead and CRM workflow for `JVT Technologies`.

## Purpose

- identify high-fit targets
- store notes and fit scores
- manage outreach status and follow-up state
- support draft generation without turning into a bulk-send system

## Core Fields

- company name
- website
- city/state
- industry
- practice area
- contact page
- public email
- notes
- fit score
- outreach status
- follow-up status
- last touched date

## Local Workflow

1. research a target manually
2. add the target through CSV or SQLite
3. score fit conservatively
4. generate a draft
5. review before any sending
6. update status after the interaction

## Current Seed Sets

- `data/fictional-seed-leads.csv`: safe example data
- `data/2026-04-09-law-firm-targets.csv`: first curated public target set for real outreach review

Use `real-lead-intake-checklist.md` when moving from fictional examples to real targets.

## Quick Start

```bash
cd /Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies/lead-pipeline
python3 tools/lead_pipeline_cli.py init-db --db data/jvt_leads.sqlite3
python3 tools/lead_pipeline_cli.py import-csv --db data/jvt_leads.sqlite3 --csv data/fictional-seed-leads.csv
python3 tools/lead_pipeline_cli.py list --db data/jvt_leads.sqlite3
```

The included seed CSV uses fictional `.example` domains so the workflow can be tested safely.
The real-target CSV is intentionally small and curated. Expand it conservatively rather than treating it like a bulk-send list.
