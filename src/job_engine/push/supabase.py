"""Push nested jobs to Supabase REST (service role).

Order: companies → locations → jobs → job_analytics → skills / job_skills.

Requires env:
  SUPABASE_URL
  SUPABASE_SERVICE_ROLE_KEY
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from job_engine.enums import (
    company_slug,
    normalize_title,
    to_ats,
    to_employment_type,
    to_salary_period,
    to_seniority,
    to_status,
    to_work_mode,
)

CHUNK = 200


def push_nested_jobs(
    jobs: list[dict[str, Any]],
    *,
    batch_size: int = CHUNK,
    dry_run: bool = False,
    full: bool = False,
    push_skills: bool = True,
    state_path: Path | None = None,
) -> int:
    """Upsert nested jobs: companies → locations → jobs → analytics → skills."""
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not dry_run and (not url or not key):
        raise RuntimeError("Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY")

    state: dict[str, str] = {}
    if state_path and not full:
        state = _load_json(state_path, {})
    next_state: dict[str, str] = dict(state) if state_path and not full else {}
    changed: list[dict[str, Any]] = []
    changed_jobs: list[dict[str, Any]] = []

    for job in jobs:
        mapped = map_job(job)
        if not mapped:
            continue
        h = content_hash(mapped)
        next_state[mapped["id"]] = h
        if full or state.get(mapped["id"]) != h:
            changed.append(mapped)
            changed_jobs.append(job)

    print(f"[push] jobs: {len(jobs):,}, changed/new: {len(changed):,}")
    if dry_run:
        print("[push] dry-run — no writes")
        return len(changed)

    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }

    pushed = 0
    with httpx.Client(timeout=60.0, headers=headers) as client:
        if changed:
            company_ids = upsert_companies(client, url, [m["company"] for m in changed], batch_size)
            location_ids = upsert_locations(
                client, url, [m["location"] for m in changed], batch_size
            )
            job_rows: list[dict[str, Any]] = []
            for m in changed:
                cid = company_ids.get(m["company"]["slug"])
                if not cid:
                    print(f"[push] skip {m['id']}: missing company id for {m['company']['slug']}")
                    continue
                row = dict(m["job"])
                row["company_id"] = cid
                row["location_id"] = location_ids.get(m["location"]["location_key"])
                job_rows.append(row)

            upsert_jobs(client, url, job_rows, batch_size)
            seed_analytics(client, url, [r["id"] for r in job_rows], batch_size)
            pushed = len(job_rows)

            if push_skills:
                pushed_ids = {r["id"] for r in job_rows}
                skill_jobs = [j for j in changed_jobs if j.get("id") in pushed_ids]
                push_job_skills(client, url, skill_jobs, batch_size)

    if state_path:
        # Merge with previous state so streaming chunks don't wipe other ids
        merged = dict(state)
        merged.update(next_state)
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(merged), encoding="utf-8")
        print(f"[push] state saved ({len(merged):,} ids) → {state_path}")
    print("[push] done")
    return pushed


def map_job(job: dict[str, Any]) -> dict[str, Any] | None:
    ats = str((job.get("source") or {}).get("ats") or "").strip().lower()
    board = str(
        (job.get("source") or {}).get("companySlug")
        or (job.get("company") or {}).get("slug")
        or ""
    ).strip()
    slug = company_slug(ats, board)
    if not job.get("id") or not slug:
        return None

    loc = job.get("location") if isinstance(job.get("location"), dict) else {}
    salary = job.get("salary") if isinstance(job.get("salary"), dict) else {}
    exp = job.get("experience") if isinstance(job.get("experience"), dict) else {}
    company = job.get("company") if isinstance(job.get("company"), dict) else {}
    scraped = _iso_or_null(job.get("scrapedAt")) or datetime.now(UTC).isoformat()
    status = to_status(job.get("status"))

    return {
        "id": job["id"],
        "company": {
            "slug": slug,
            "name": company.get("name") or board,
            "website": company.get("website"),
            "logo": company.get("logo"),
            "industry": company.get("industry"),
            "size": company.get("size"),
            "type": company.get("type"),
        },
        "location": {
            "location_key": location_key(loc),
            "country": loc.get("country"),
            "state": loc.get("state"),
            "city": loc.get("city"),
            "formatted": loc.get("formatted"),
            "latitude": loc.get("latitude"),
            "longitude": loc.get("longitude"),
        },
        "job": {
            "id": job["id"],
            "title": job.get("title") or "",
            "normalized_title": normalize_title(job.get("title")),
            "department": job.get("department"),
            "team": job.get("team"),
            "summary": job.get("summary"),
            "description": job.get("description"),
            "employment_type": to_employment_type(job.get("employmentType")),
            "work_mode": to_work_mode(job.get("workMode")),
            "seniority": to_seniority(job.get("seniority")),
            "min_experience": _clamp_years(exp.get("min")),
            "max_experience": _clamp_years(exp.get("max")),
            "salary_currency": (
                str(salary["currency"])[:3].upper() if salary.get("currency") else None
            ),
            "salary_min": _num(salary.get("min")),
            "salary_max": _num(salary.get("max")),
            "salary_period": to_salary_period(salary.get("period")),
            "salary_visible": bool(salary.get("min") is not None or salary.get("max") is not None),
            "vacancies": 1,
            "apply_url": (job.get("source") or {}).get("applyUrl"),
            "detail_api_url": (job.get("source") or {}).get("detailApiUrl"),
            "ats": to_ats(ats),
            "external_id": str((job.get("source") or {}).get("externalId") or ""),
            "posted_at": _iso_or_null(job.get("postedAt")),
            "updated_at": _iso_or_null(job.get("updatedAt")),
            "last_scraped_at": scraped,
            "status": status,
            "expired": status == 4,
            "language": job.get("language"),
        },
    }


def content_hash(mapped: dict[str, Any]) -> str:
    stable = {
        "title": mapped["job"]["title"],
        "company": mapped["company"],
        "location": mapped["location"],
        "employment_type": mapped["job"]["employment_type"],
        "work_mode": mapped["job"]["work_mode"],
        "seniority": mapped["job"]["seniority"],
        "min_experience": mapped["job"]["min_experience"],
        "max_experience": mapped["job"]["max_experience"],
        "salary_min": mapped["job"]["salary_min"],
        "salary_max": mapped["job"]["salary_max"],
        "apply_url": mapped["job"]["apply_url"],
        "status": mapped["job"]["status"],
        "posted_at": mapped["job"]["posted_at"],
        "updated_at": mapped["job"]["updated_at"],
    }
    return hashlib.sha1(json.dumps(stable, sort_keys=True, default=str).encode()).hexdigest()


def location_key(loc: dict[str, Any]) -> str:
    country = str(loc.get("country") or "").strip().lower()
    state = str(loc.get("state") or "").strip().lower()
    city = str(loc.get("city") or "").strip().lower()
    if country or state or city:
        return f"{country}|{state}|{city}"
    formatted = str(loc.get("formatted") or "").strip().lower()
    return f"fmt:{formatted}" if formatted else "unknown"


def upsert_companies(
    client: httpx.Client, base: str, companies: list[dict[str, Any]], chunk: int
) -> dict[str, int]:
    by_slug: dict[str, dict[str, Any]] = {}
    now = datetime.now(UTC).isoformat()
    for c in companies:
        slug = c.get("slug")
        if not slug or slug in by_slug:
            continue
        by_slug[slug] = {
            "slug": slug,
            "name": c.get("name") or slug,
            "logo": c.get("logo"),
            "website": c.get("website"),
            "industry": c.get("industry"),
            "size": c.get("size"),
            "type": c.get("type"),
            "updated_at": now,
        }
    rows = list(by_slug.values())
    id_by_slug: dict[str, int] = {}
    for i in range(0, len(rows), chunk):
        batch = rows[i : i + chunk]
        r = client.post(
            f"{base}/rest/v1/companies?on_conflict=slug",
            headers={"Prefer": "resolution=merge-duplicates,return=representation"},
            json=batch,
        )
        r.raise_for_status()
        for row in r.json() or []:
            id_by_slug[row["slug"]] = row["id"]
        print(f"[push] companies: {min(i + chunk, len(rows))}/{len(rows)}")
    missing = [r["slug"] for r in rows if r["slug"] not in id_by_slug]
    _fill_ids(client, base, "companies", "slug", missing, id_by_slug)
    return id_by_slug


def upsert_locations(
    client: httpx.Client, base: str, locations: list[dict[str, Any]], chunk: int
) -> dict[str, int]:
    by_key: dict[str, dict[str, Any]] = {}
    for loc in locations:
        key = loc.get("location_key")
        if key and key not in by_key:
            by_key[key] = loc
    rows = list(by_key.values())
    id_by_key: dict[str, int] = {}
    for i in range(0, len(rows), chunk):
        batch = rows[i : i + chunk]
        r = client.post(
            f"{base}/rest/v1/locations?on_conflict=location_key",
            headers={"Prefer": "resolution=merge-duplicates,return=representation"},
            json=batch,
        )
        r.raise_for_status()
        for row in r.json() or []:
            id_by_key[row["location_key"]] = row["id"]
        print(f"[push] locations: {min(i + chunk, len(rows))}/{len(rows)}")
    missing = [r["location_key"] for r in rows if r["location_key"] not in id_by_key]
    _fill_ids(client, base, "locations", "location_key", missing, id_by_key)
    return id_by_key


def upsert_jobs(
    client: httpx.Client, base: str, job_rows: list[dict[str, Any]], chunk: int
) -> None:
    for i in range(0, len(job_rows), chunk):
        batch = job_rows[i : i + chunk]
        r = client.post(
            f"{base}/rest/v1/jobs?on_conflict=id",
            headers={"Prefer": "resolution=merge-duplicates,return=minimal"},
            json=batch,
        )
        r.raise_for_status()
        print(f"[push] jobs: {min(i + chunk, len(job_rows))}/{len(job_rows)}")


def seed_analytics(
    client: httpx.Client, base: str, job_ids: list[str], chunk: int
) -> None:
    rows = [
        {"job_id": jid, "views": 0, "clicks": 0, "applications": 0, "saved": 0}
        for jid in job_ids
    ]
    for i in range(0, len(rows), chunk):
        batch = rows[i : i + chunk]
        r = client.post(
            f"{base}/rest/v1/job_analytics?on_conflict=job_id",
            headers={"Prefer": "resolution=ignore-duplicates,return=minimal"},
            json=batch,
        )
        r.raise_for_status()
        print(f"[push] job_analytics seed: {min(i + chunk, len(rows))}/{len(rows)}")


def push_job_skills(
    client: httpx.Client,
    base: str,
    jobs: list[dict[str, Any]],
    chunk: int,
) -> None:
    """Upsert skill names + job_skills links (source=regex)."""
    skill_cache: dict[str, int] = {}
    links: list[dict[str, Any]] = []
    now = datetime.now(UTC).isoformat()

    for job in jobs:
        jid = job.get("id")
        if not jid:
            continue
        skill_block = job.get("skills") if isinstance(job.get("skills"), dict) else {}
        for name in skill_block.get("required") or []:
            sid = _ensure_skill(client, base, str(name), skill_cache, now)
            if sid is not None:
                links.append({"job_id": jid, "skill_id": sid, "source": "regex"})
        for name in skill_block.get("preferred") or []:
            sid = _ensure_skill(client, base, str(name), skill_cache, now)
            if sid is not None:
                links.append({"job_id": jid, "skill_id": sid, "source": "regex"})

    # dedupe
    seen: set[tuple[str, int]] = set()
    uniq: list[dict[str, Any]] = []
    for link in links:
        key = (link["job_id"], link["skill_id"])
        if key in seen:
            continue
        seen.add(key)
        uniq.append(link)

    for i in range(0, len(uniq), chunk):
        batch = uniq[i : i + chunk]
        r = client.post(
            f"{base}/rest/v1/job_skills?on_conflict=job_id,skill_id",
            headers={"Prefer": "resolution=merge-duplicates,return=minimal"},
            json=batch,
        )
        r.raise_for_status()
        print(f"[push] job_skills: {min(i + chunk, len(uniq))}/{len(uniq)}")


def _ensure_skill(
    client: httpx.Client,
    base: str,
    name: str,
    cache: dict[str, int],
    now: str,
) -> int | None:
    key = re.sub(r"\s+", " ", name.strip().lower())
    if not key:
        return None
    if key in cache:
        return cache[key]
    r = client.get(
        f"{base}/rest/v1/skills",
        params={"normalized_name": f"eq.{key}", "select": "id", "limit": "1"},
    )
    r.raise_for_status()
    rows = r.json() or []
    if rows:
        cache[key] = rows[0]["id"]
        return cache[key]
    r = client.post(
        f"{base}/rest/v1/skills?on_conflict=normalized_name",
        headers={"Prefer": "resolution=merge-duplicates,return=representation"},
        json=[{"name": key, "normalized_name": key, "last_seen": now}],
    )
    r.raise_for_status()
    created = r.json() or []
    if created:
        cache[key] = created[0]["id"]
        return cache[key]
    # conflict may return empty — lookup again
    r = client.get(
        f"{base}/rest/v1/skills",
        params={"normalized_name": f"eq.{key}", "select": "id", "limit": "1"},
    )
    r.raise_for_status()
    rows = r.json() or []
    if rows:
        cache[key] = rows[0]["id"]
        return cache[key]
    return None


def _fill_ids(
    client: httpx.Client,
    base: str,
    table: str,
    col: str,
    missing: list[str],
    out: dict[str, int],
) -> None:
    for i in range(0, len(missing), 50):
        slice_ = missing[i : i + 50]
        if not slice_:
            continue
        filt = ",".join(f'"{_escape_id(s)}"' for s in slice_)
        r = client.get(
            f"{base}/rest/v1/{table}",
            params={"select": f"id,{col}", f"{col}": f"in.({filt})"},
        )
        r.raise_for_status()
        for row in r.json() or []:
            out[row[col]] = row["id"]


def _load_json(path: Path, fallback: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return fallback


def _iso_or_null(value: object) -> str | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).isoformat()
    except ValueError:
        return None


def _clamp_years(n: object) -> int | None:
    if n is None or n == "":
        return None
    try:
        v = int(float(n))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return max(0, min(50, v))


def _num(n: object) -> float | None:
    if n is None or n == "":
        return None
    try:
        return float(n)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _escape_id(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')
