"""Copy Postgres into nested MongoDB.

Env: DATABASE_URL, MONGODB_URI
Uses a server-side cursor — not PostgREST.
"""

from __future__ import annotations

import os
from typing import Any

import psycopg
from psycopg.rows import dict_row

from job_engine.push.mongo_docs import (
    flush_job_skills,
    write_analytics,
    write_companies,
    write_jobs,
    write_skills,
)
from job_engine.push.mongo import get_db

FETCH = 5000
WRITE = 500


def migrate() -> dict[str, int]:
    dsn = os.environ.get("DATABASE_URL", "").strip()
    if not dsn:
        raise RuntimeError("Set DATABASE_URL (Postgres URI)")
    if "sslmode=" not in dsn:
        dsn += ("&" if "?" in dsn else "?") + "sslmode=require"

    db = get_db()
    counts: dict[str, int] = {}
    with psycopg.connect(dsn, row_factory=dict_row, connect_timeout=30) as conn:
        conn.autocommit = False
        companies = list(_cursor(conn, "companies", COMPANY_SQL))
        counts["companies"] = write_companies(db, companies)
        company_by_id = {c["id"]: c for c in companies}
        print(f"[migrate-pg] companies {len(companies)}", flush=True)

        locations = {row["id"]: row for row in _cursor(conn, "locations", LOCATION_SQL)}
        print(f"[migrate-pg] locations {len(locations)}", flush=True)

        skills_rows = list(_cursor(conn, "skills", SKILL_SQL))
        skill_by_id = {s["id"]: s for s in skills_rows}
        counts["skills"] = write_skills(db, skills_rows)
        print(f"[migrate-pg] skills {len(skills_rows)}", flush=True)

        job_count = 0
        batch: list[dict[str, Any]] = []
        for row in _cursor(conn, "jobs", JOB_SQL):
            batch.append(row)
            if len(batch) >= WRITE:
                job_count += write_jobs(db, batch, company_by_id, locations, {})
                batch = []
        if batch:
            job_count += write_jobs(db, batch, company_by_id, locations, {})
        counts["jobs"] = job_count
        print(f"[migrate-pg] jobs {job_count}", flush=True)

        skill_links: dict[str, list[str]] = {}
        flushed = 0
        for link in _cursor(conn, "job_skills", JOB_SKILL_SQL):
            sk = skill_by_id.get(link["skill_id"])
            name = (sk or {}).get("normalized_name") or (sk or {}).get("name")
            if not name or not link.get("job_id"):
                continue
            key = str(name).strip().lower()
            skill_links.setdefault(link["job_id"], [])
            if key not in skill_links[link["job_id"]]:
                skill_links[link["job_id"]].append(key)
            if len(skill_links) >= WRITE:
                flushed += flush_job_skills(db, skill_links)
                skill_links = {}
        if skill_links:
            flushed += flush_job_skills(db, skill_links)
        print(f"[migrate-pg] job_skills jobs={flushed}", flush=True)

        analytics_batch: list[dict[str, Any]] = []
        analytics_count = 0
        for row in _cursor(conn, "job_analytics", ANALYTICS_SQL):
            analytics_batch.append(row)
            if len(analytics_batch) >= WRITE:
                analytics_count += write_analytics(db, analytics_batch)
                analytics_batch = []
        if analytics_batch:
            analytics_count += write_analytics(db, analytics_batch)
        counts["job_analytics"] = analytics_count

    print(f"[migrate-pg] done {counts}", flush=True)
    return counts


def _cursor(conn, label: str, sql: str):
    n = 0
    with conn.cursor(name=f"mig_{label}") as cur:
        cur.itersize = FETCH
        cur.execute(sql)
        while True:
            rows = cur.fetchmany(FETCH)
            if not rows:
                break
            n += len(rows)
            print(f"[migrate-pg] {label} {n}", flush=True)
            yield from rows


COMPANY_SQL = """
SELECT id, slug, name, industry, website, logo, size, type
FROM public.companies
ORDER BY id
"""

LOCATION_SQL = """
SELECT id, location_key, country, state, city, formatted, latitude, longitude
FROM public.locations
ORDER BY id
"""

SKILL_SQL = """
SELECT id, name, normalized_name
FROM public.skills
ORDER BY id
"""

JOB_SQL = """
SELECT id, title, normalized_title, department, team, employment_type, work_mode, seniority,
       min_experience, max_experience, salary_currency, salary_min, salary_max, salary_period,
       salary_visible, vacancies, apply_url, detail_api_url, ats, external_id, posted_at,
       updated_at, last_scraped_at, status, expired, language, company_id, location_id
FROM public.jobs
ORDER BY id
"""

JOB_SKILL_SQL = """
SELECT job_id, skill_id
FROM public.job_skills
ORDER BY job_id
"""

ANALYTICS_SQL = """
SELECT job_id, views, clicks, applications, saved, updated_at
FROM public.job_analytics
ORDER BY job_id
"""
