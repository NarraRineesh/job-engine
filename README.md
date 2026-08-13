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
```

Put secrets in repo-root `.env` (gitignored). See [`.env.example`](.env.example):

```bash
SUPABASE_URL=...
SUPABASE_PUBLISHABLE_KEY=...
SUPABASE_SECRET_KEY=...
SUPABASE_JWKS_URL=...
TYPESENSE_API_KEY=xyz
```

## Run (Python scrape)

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

## API (JavaScript + Typesense)

Read APIs live under [`api/`](api/). Jobs / companies / skills **search** go through Typesense. Analytics, trending, and company-trend series use Supabase RPCs.

```bash
# 1. Start Typesense (Docker Desktop must be running)
docker compose up -d

# 2. Install + sync index from Supabase
cd api
npm install
npm run index

# 3. Serve HTTP API
npm run dev   # http://localhost:8787/v1/jobs
```

Useful routes:

| Method | Path | Backend |
|--------|------|---------|
| GET | `/v1/jobs?q=engineer` | Typesense |
| GET | `/v1/jobs/:id` | Typesense + analytics |
| GET | `/v1/companies` | Typesense |
| GET | `/v1/skills` | Typesense |
| GET | `/v1/jobs/trending` | Supabase RPC |
| GET | `/v1/skills/trending` | Supabase RPC |
| GET | `/v1/trends/companies` | Supabase RPC |
| GET | `/v1/companies/:slug/trends` | Supabase RPC |
| GET/POST | `/v1/jobs/:id/analytics` | Supabase |
| GET | `/v1/stats` | Typesense counts |

Re-run `npm run index` after a stream so Typesense stays current.

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
Runs weekly (Monday 02:30 UTC) and on demand. A new run **cancels** an in-progress stream.  
Empty `ats` = scrapeable ATS only; empty `country` = no filter. Default enrich is `python` (lexicon skills).  
GitHub allows 256 matrix jobs; `plan-chunks` raises `--chunk-size` if needed so a full run fits.  
Push writes companies, locations, jobs, job_analytics, skills, and job_skills. Job **summary** and **description** are not stored (used only locally to extract skills).  
Secrets: `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`. Optional: `CURSOR_API_KEY` for `--enrich both`.

## Layout

```text
src/job_engine/         # Python scrape → enrich → push
api/                    # JavaScript read API (Typesense + Supabase)
docker-compose.yml      # local Typesense :8108
supabase/migrations/    # schema + RPCs
```

CLI surface: `run` | `plan-chunks`.
