"""Bulk upsert helpers for Postgres → Mongo migrate."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pymongo import UpdateOne

from job_engine.push.mongo import _as_dt, _bulk


def flush_job_skills(db, skill_links: dict[str, list[str]]) -> int:
    ops = [
        UpdateOne({"_id": jid}, {"$addToSet": {"skills": {"$each": names}}})
        for jid, names in skill_links.items()
        if names
    ]
    _bulk(db.jobs, ops, "migrate job_skills")
    return len(ops)


def write_companies(db, rows: list[dict[str, Any]]) -> int:
    now = datetime.now(UTC)
    ops = []
    for c in rows:
        slug = c.get("slug")
        if not slug:
            continue
        ops.append(
            UpdateOne(
                {"_id": slug},
                {
                    "$set": {
                        "slug": slug,
                        "name": c.get("name") or slug,
                        "industry": c.get("industry"),
                        "website": c.get("website"),
                        "logo": c.get("logo"),
                        "size": c.get("size"),
                        "type": c.get("type"),
                        "updated_at": now,
                        "pg_id": c.get("id"),
                    }
                },
                upsert=True,
            )
        )
    _bulk(db.companies, ops, "migrate companies")
    return len(ops)


def write_skills(db, rows: list[dict[str, Any]]) -> int:
    now = datetime.now(UTC)
    ops = []
    for s in rows:
        name = (s.get("normalized_name") or s.get("name") or "").strip().lower()
        if not name:
            continue
        ops.append(
            UpdateOne(
                {"_id": name},
                {
                    "$set": {
                        "name": s.get("name") or name,
                        "normalized_name": name,
                        "last_seen": now,
                    }
                },
                upsert=True,
            )
        )
    _bulk(db.skills, ops, "migrate skills")
    return len(ops)


def write_jobs(db, jobs, company_by_id, locations, job_skills) -> int:
    ops = []
    for j in jobs:
        jid = j.get("id")
        if not jid:
            continue
        company = company_by_id.get(j.get("company_id")) or {}
        loc = locations.get(j.get("location_id")) or {}
        slug = company.get("slug") or f"company:{j.get('company_id') or 'unknown'}"
        ops.append(
            UpdateOne(
                {"_id": jid},
                {
                    "$set": {
                        "_id": jid,
                        "title": j.get("title") or "",
                        "normalized_title": j.get("normalized_title") or "",
                        "department": j.get("department"),
                        "team": j.get("team"),
                        "employment_type": j.get("employment_type"),
                        "work_mode": j.get("work_mode"),
                        "seniority": j.get("seniority"),
                        "min_experience": j.get("min_experience"),
                        "max_experience": j.get("max_experience"),
                        "salary_currency": j.get("salary_currency"),
                        "salary_min": j.get("salary_min"),
                        "salary_max": j.get("salary_max"),
                        "salary_period": j.get("salary_period"),
                        "salary_visible": j.get("salary_visible"),
                        "vacancies": j.get("vacancies"),
                        "apply_url": j.get("apply_url"),
                        "detail_api_url": j.get("detail_api_url"),
                        "ats": j.get("ats"),
                        "external_id": j.get("external_id"),
                        "posted_at": _as_dt(j.get("posted_at")),
                        "updated_at": _as_dt(j.get("updated_at")),
                        "last_scraped_at": _as_dt(j.get("last_scraped_at")),
                        "status": j.get("status") if j.get("status") is not None else 1,
                        "expired": j.get("expired"),
                        "language": j.get("language"),
                        "company": {"slug": slug, "name": company.get("name") or slug},
                        "location": {
                            "location_key": loc.get("location_key"),
                            "country": loc.get("country"),
                            "state": loc.get("state"),
                            "city": loc.get("city"),
                            "formatted": loc.get("formatted"),
                            "latitude": loc.get("latitude"),
                            "longitude": loc.get("longitude"),
                        },
                        "skills": job_skills.get(jid) or [],
                    }
                },
                upsert=True,
            )
        )
    _bulk(db.jobs, ops, "migrate jobs")
    return len(ops)


def write_analytics(db, rows: list[dict[str, Any]]) -> int:
    ops = []
    for a in rows:
        jid = a.get("job_id")
        if not jid:
            continue
        ops.append(
            UpdateOne(
                {"_id": jid},
                {
                    "$set": {
                        "job_id": jid,
                        "views": a.get("views") or 0,
                        "clicks": a.get("clicks") or 0,
                        "applications": a.get("applications") or 0,
                        "saved": a.get("saved") or 0,
                        "updated_at": _as_dt(a.get("updated_at")),
                    }
                },
                upsert=True,
            )
        )
    _bulk(db.job_analytics, ops, "migrate analytics")
    return len(ops)
