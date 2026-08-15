# job-engine

Simple loop: **fetch ATS jobs → enrich → push MongoDB → keep track**.

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
MONGODB_URI=mongodb://jobengine:changeme@127.0.0.1:27017/jobengine?authSource=admin
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

# Smoke without Mongo
uv run job-engine run --ats keka --max-tenants 3 --skip-push
```

## API (JavaScript + Typesense)

Read APIs live under [`api/`](api/). Jobs / companies / skills **search** go through Typesense. Analytics, trending, and company-trend series use MongoDB.

```bash
# 1. Start Typesense on 127.0.0.1:8108 (Docker Desktop must be running)
docker compose up -d

# 2. Install + sync index from Mongo
cd api
npm install
npm run index

# 3. Serve HTTP API
npm run dev   # http://localhost:8787/v1/jobs
```

Production (Hetzner CX33 `157.180.95.193`): Mongo + Typesense in Docker, Node on the host, Nginx TLS at `https://api.glowminds.in`. See [`deploy/README.md`](deploy/README.md).

### Health

| Method | Path | Backend | Notes |
|--------|------|---------|--------|
| GET | `/health` | — | `{ "ok": true }` |

### Jobs

| Method | Path | Backend | Query / body |
|--------|------|---------|----------------|
| GET | `/v1/jobs` | Typesense | `q` (default `*`), `status` (default `active`), `ats`, `work_mode`, `company` (slug), `country`, `skill`, `limit`, `page` |
| GET | `/v1/jobs/featured` | Mongo featured score | `limit` |
| GET | `/v1/jobs/trending` | Mongo trending | `days` (default 14), `limit` |
| GET | `/v1/jobs/:id` | Typesense + `job_analytics` | Job document plus analytics row |
| GET | `/v1/jobs/:id/similar` | Typesense | `limit` — similar by title + shared skills |
| GET | `/v1/jobs/:id/analytics` | Mongo | `{ job_id, views, clicks, applications, saved }` |
| POST | `/v1/jobs/:id/analytics` | Mongo increment | JSON `{ "metric": "views" \| "clicks" \| "applications" \| "saved" }` |

### Companies

| Method | Path | Backend | Query / body |
|--------|------|---------|----------------|
| GET | `/v1/companies` | Typesense | `q` (name/slug/industry), `limit`, `page` |
| GET | `/v1/companies/:slug` | Typesense | Company document |
| GET | `/v1/companies/:slug/jobs` | Typesense | `q`, `limit`, `page` — active jobs for that slug |
| GET | `/v1/companies/:slug/trends` | Mongo monthly counts | `months` (1–24, default 6) |

### Skills

| Method | Path | Backend | Query / body |
|--------|------|---------|----------------|
| GET | `/v1/skills` | Typesense | `q` (name), `limit`, `page` |
| GET | `/v1/skills/trending` | Mongo | `days` (default 30), `limit` |
| GET | `/v1/skills/:name` | Typesense | Skill by `normalized_name` |
| GET | `/v1/skills/:name/jobs` | Typesense | `q`, `limit`, `page` — jobs tagged with that skill |

### Trends + stats

| Method | Path | Backend | Query / body |
|--------|------|---------|----------------|
| GET | `/v1/trends/jobs` | Mongo | `days` (default 14), `limit` |
| GET | `/v1/trends/skills` | Mongo | `days` (default 30), `limit` |
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
uv run job-engine plan-chunks --mode multi_tenant
```

Inventories: `data/companies/ats-companies/{ats}.json`.

## GitHub Actions

Two workflows, separate concurrency groups (one does not cancel the other):

| Workflow | File | What | Schedule |
|----------|------|------|----------|
| `stream-multi` | `.github/workflows/stream.yml` | Company boards (Ashby, Greenhouse, …) | Monday 02:30 UTC |
| `stream-singleton` | `.github/workflows/stream-singleton.yml` | One-board sources (EURES, Apple, Amazon, …) | Tuesday 02:30 UTC |

Both also run on demand. Retriggering a workflow cancels only **that** workflow’s in-progress run.

- **One GitHub job per ATS** (registry order: ADP → Ashby → …). Up to 8 ATS jobs in parallel for multi, 4 for singleton.
- Inside an ATS job, **8 company boards at a time** (pipelined: when one finishes, the next starts).
- Weekly singleton **skips EURES and Bundesagentur** (`"stream": false`). Run them on purpose: `uv run job-engine run --ats eures`.

Empty `ats` = streamable ATS of that mode; empty `country` = no filter. Default enrich is `python`.  
Local: `uv run job-engine plan-chunks --mode multi_tenant`.  
Push writes companies, jobs (embedded location + skills), job_analytics, and skills. Job **summary** and **description** are not stored (used only locally to extract skills).  
Secrets: `MONGODB_URI` (localhost URI; Actions SSH-tunnels to the CX33), `HETZNER_HOST` (`157.180.95.193`), `HETZNER_SSH_KEY` (private key `hetzner_cx33_gha`), optional `HETZNER_USER` (`root`). Optional: `CURSOR_API_KEY` for `--enrich both`. One-shot copy: `uv run job-engine migrate-postgres`.

## Layout

```text
src/job_engine/         # Python scrape → enrich → push Mongo
api/                    # JavaScript read API (Typesense + Mongo)
docker-compose.yml      # Typesense 8108 + Mongo 27017 on loopback
deploy/                 # Hetzner CX33: systemd + Nginx (api.glowminds.in)
```

CLI surface: `run` | `plan-chunks` | `migrate-postgres`.
