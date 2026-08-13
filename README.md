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

Base URL: `http://localhost:8787`. Pagination on list/search: `limit` (1–100, default 20) and `page` (default 1).

### Health

| Method | Path | Backend | Notes |
|--------|------|---------|--------|
| GET | `/health` | — | `{ "ok": true }` |

### Jobs

| Method | Path | Backend | Query / body |
|--------|------|---------|----------------|
| GET | `/v1/jobs` | Typesense | `q` (default `*`), `status` (default `active`), `ats`, `work_mode`, `company` (slug), `country`, `skill`, `limit`, `page` |
| GET | `/v1/jobs/featured` | Supabase `featured_jobs` | `limit` |
| GET | `/v1/jobs/trending` | Supabase `trending_jobs` | `days` (default 14), `limit` |
| GET | `/v1/jobs/:id` | Typesense + `job_analytics` | Job document plus analytics row |
| GET | `/v1/jobs/:id/similar` | Typesense | `limit` — similar by title + shared skills |
| GET | `/v1/jobs/:id/analytics` | Supabase | `{ job_id, views, clicks, applications, saved }` |
| POST | `/v1/jobs/:id/analytics` | Supabase `increment_job_analytics` | JSON `{ "metric": "views" \| "clicks" \| "applications" \| "saved" }` |

### Companies

| Method | Path | Backend | Query / body |
|--------|------|---------|----------------|
| GET | `/v1/companies` | Typesense | `q` (name/slug/industry), `limit`, `page` |
| GET | `/v1/companies/:slug` | Typesense | Company document |
| GET | `/v1/companies/:slug/jobs` | Typesense | `q`, `limit`, `page` — active jobs for that slug |
| GET | `/v1/companies/:slug/trends` | Supabase `company_trends_live` | `months` (1–24, default 6) |

### Skills

| Method | Path | Backend | Query / body |
|--------|------|---------|----------------|
| GET | `/v1/skills` | Typesense | `q` (name), `limit`, `page` |
| GET | `/v1/skills/trending` | Supabase `trending_skills_by_window` | `days` (default 30), `limit` |
| GET | `/v1/skills/:name` | Typesense | Skill by `normalized_name` |
| GET | `/v1/skills/:name/jobs` | Typesense | `q`, `limit`, `page` — jobs tagged with that skill |

### Trends + stats

| Method | Path | Backend | Query / body |
|--------|------|---------|----------------|
| GET | `/v1/trends/jobs` | Supabase `trending_jobs` | `days` (default 14), `limit` |
| GET | `/v1/trends/skills` | Supabase `trending_skills_by_window` | `days` (default 30), `limit` |
| GET | `/v1/trends/companies` | Typesense | `limit`, `page` — ranked by `active_job_count` |
| GET | `/v1/stats` | Typesense | `{ total_jobs, active_jobs, companies, skills, source }` |

Examples:

```bash
curl http://localhost:8787/health
curl 'http://localhost:8787/v1/jobs?q=engineer&country=United%20States&limit=5'
curl http://localhost:8787/v1/jobs/ashby:docker:abc123
curl -X POST http://localhost:8787/v1/jobs/ashby:docker:abc123/analytics \
  -H 'content-type: application/json' \
  -d '{"metric":"views"}'
curl 'http://localhost:8787/v1/companies?q=stripe'
curl http://localhost:8787/v1/companies/ashby:stripe/trends
curl 'http://localhost:8787/v1/skills?q=python'
curl http://localhost:8787/v1/skills/trending
curl http://localhost:8787/v1/trends/companies
curl http://localhost:8787/v1/stats
```

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
