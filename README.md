# job-engine

Simple loop: **fetch ATS jobs → enrich → push Supabase → keep track**.

```text
company (from JSON)
   → scrape board
   → enrich (python parser  |  Cursor SDK gaps  |  both)
   → push company + jobs + skills
   → track progress
```

All ATS scrapers stay under `fetch/scrapers/`. Each ATS has a dedicated parser under `parsers/` (unknown ATS uses the shared base parser).

## Setup

```bash
uv sync --extra dev
# optional Cursor enrich:
uv sync --extra cursor
export CURSOR_API_KEY=...
```

## Run

```bash
# Python enrich only (default)
uv run job-engine run --ats keka --concurrency 8

# Optional country filter
uv run job-engine run --ats keka --country IN

# Python + Cursor gap-fill for skills/location/experience/company
uv run job-engine run --ats keka --enrich both

# Cursor-only gap path (still runs ATS parser first for structure)
uv run job-engine run --ats keka --enrich cursor

# Smoke without Supabase
uv run job-engine run --ats keka --max-tenants 3 --skip-push
```

Supabase:

```bash
export SUPABASE_URL=...
export SUPABASE_SERVICE_ROLE_KEY=...
```

## Tracking

| File | What |
|------|------|
| `out/push-state.json` | job id → content hash (skip unchanged pushes) |
| `out/track.json` | per-tenant last scrape: jobs fetched/pushed, errors |
| `data/corpus/{ats}.jsonl` | optional local job log |

## Companies

```bash
uv run job-engine plan-chunks --ats keka --chunk-size 50
```

Inventories: `data/companies/ats-companies/{ats}.json`.

## GitHub Actions

`.github/workflows/stream.yml` — ATS × tenant chunks (`max-parallel: 8`).  
Empty `ats` = all registered; empty `country` = no filter.  
Secrets: `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`. Optional: `CURSOR_API_KEY` for `--enrich both`.

## Layout

```text
src/job_engine/
  fetch/scrapers/   # all ATS scrapers
  parsers/          # per-ATS python enrich
  enrich/           # python + optional Cursor SDK
  pipeline/         # run_stream only
  push/             # Supabase upsert
  track.py          # per-tenant progress
  companies.py / cli.py
```

CLI surface: `run` | `plan-chunks`.
