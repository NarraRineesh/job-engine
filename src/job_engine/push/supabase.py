"""Push nested jobs to Supabase REST (service role).

Order: companies → locations → jobs → job_analytics → skills / job_skills.

Requires env:
  SUPABASE_URL
  SUPABASE_SERVICE_ROLE_KEY
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import threading
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
_STATE_LOCK = threading.Lock()


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
        with _STATE_LOCK:
            loaded = _load_json(state_path, {})
            state = loaded if isinstance(loaded, dict) else {}
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
                row = _omit_none(dict(m["job"]))
                row["company_id"] = cid
                row["location_id"] = location_ids.get(m["location"]["location_key"])
                job_rows.append(row)

            pushed_ids = upsert_jobs(client, url, job_rows, batch_size)
            seed_analytics(client, url, pushed_ids, batch_size)
            pushed = len(pushed_ids)

            if push_skills:
                ok = set(pushed_ids)
                skill_jobs = [j for j in changed_jobs if j.get("id") in ok]
                push_job_skills(client, url, skill_jobs, batch_size)

    if state_path:
        with _STATE_LOCK:
            prev = _load_json(state_path, {})
            if not isinstance(prev, dict):
                prev = {}
            prev.update(next_state)
            state_path.parent.mkdir(parents=True, exist_ok=True)
            state_path.write_text(json.dumps(prev), encoding="utf-8")
            print(f"[push] state saved ({len(prev):,} ids) → {state_path}")
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
            "country": _as_text(loc.get("country"), 120),
            "state": _as_text(loc.get("state"), 120),
            "city": _as_text(loc.get("city"), 200),
            "formatted": _as_text(loc.get("formatted"), 500),
            "latitude": _coord(loc.get("latitude"), 90),
            "longitude": _coord(loc.get("longitude"), 180),
        },
        "job": {
            # description/summary stay local for skill extract; not stored in Supabase
            "id": job["id"],
            "title": job.get("title") or "",
            "normalized_title": normalize_title(job.get("title")),
            "department": job.get("department"),
            "team": job.get("team"),
            "employment_type": _enum_or_none(to_employment_type(job.get("employmentType")), 1, 6),
            "work_mode": _enum_or_none(to_work_mode(job.get("workMode")), 1, 3),
            "seniority": _enum_or_none(to_seniority(job.get("seniority")), 1, 10),
            "min_experience": _clamp_years(exp.get("min")),
            "max_experience": _clamp_years(exp.get("max")),
            "salary_currency": _currency(salary.get("currency")),
            "salary_min": _int4(salary.get("min")),
            "salary_max": _int4(salary.get("max")),
            "salary_period": _enum_or_none(to_salary_period(salary.get("period")), 1, 3),
            "salary_visible": bool(salary.get("min") is not None or salary.get("max") is not None),
            "vacancies": 1,
            "apply_url": (job.get("source") or {}).get("applyUrl"),
            "detail_api_url": (job.get("source") or {}).get("detailApiUrl"),
            "ats": to_ats(ats),
            "external_id": str((job.get("source") or {}).get("externalId") or ""),
            "posted_at": _iso_or_null(job.get("postedAt")),
            "updated_at": _iso_or_null(job.get("updatedAt")),
            "last_scraped_at": scraped,
            "status": _enum_or_none(status, 1, 4) or 1,
            "expired": status == 4,
            "language": _language(job.get("language")),
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
        by_slug[slug] = _omit_none({
            "slug": slug,
            "name": c.get("name") or slug,
            "logo": c.get("logo"),
            "website": c.get("website"),
            "industry": c.get("industry"),
            "size": c.get("size"),
            "type": c.get("type"),
            "updated_at": now,
        })
    rows = list(by_slug.values())
    id_by_slug: dict[str, int] = {}
    for i in range(0, len(rows), chunk):
        batch = rows[i : i + chunk]
        r = client.post(
            f"{base}/rest/v1/companies?on_conflict=slug",
            headers={"Prefer": "resolution=merge-duplicates,return=representation"},
            json=batch,
        )
        _raise_http(r, "companies")
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
        row = _location_row(loc)
        if row and row["location_key"] not in by_key:
            by_key[row["location_key"]] = row
    rows = list(by_key.values())
    id_by_key: dict[str, int] = {}
    url = f"{base}/rest/v1/locations?on_conflict=location_key"
    for i in range(0, len(rows), chunk):
        _upsert_location_chunk(client, url, rows[i : i + chunk], id_by_key)
        print(f"[push] locations: {min(i + chunk, len(rows))}/{len(rows)}")
    missing = [r["location_key"] for r in rows if r["location_key"] not in id_by_key]
    _fill_ids(client, base, "locations", "location_key", missing, id_by_key)
    return id_by_key


def _location_row(loc: dict[str, Any]) -> dict[str, Any] | None:
    """One locations-table row with a *fixed* key set.

    PostgREST bulk insert 400s when objects in the same payload have
    different keys (``_omit_none`` dropped lat/lon on some rows). Always
    send the same columns; use JSON nulls.
    """
    key = str(loc.get("location_key") or "").strip()
    if not key:
        return None
    return {
        "location_key": key[:500],
        "country": _as_text(loc.get("country"), 120),
        "state": _as_text(loc.get("state"), 120),
        "city": _as_text(loc.get("city"), 200),
        "formatted": _as_text(loc.get("formatted"), 500),
        "latitude": _coord(loc.get("latitude"), 90),
        "longitude": _coord(loc.get("longitude"), 180),
    }


def _upsert_location_chunk(
    client: httpx.Client,
    url: str,
    batch: list[dict[str, Any]],
    id_by_key: dict[str, int],
) -> None:
    if not batch:
        return
    r = client.post(
        url,
        headers={"Prefer": "resolution=merge-duplicates,return=representation"},
        json=batch,
    )
    if r.is_success:
        for row in r.json() or []:
            id_by_key[row["location_key"]] = row["id"]
        return
    detail = (r.text or "")[:1500]
    if r.status_code == 400 and len(batch) > 1:
        print(f"[push] locations 400 on {len(batch)} rows, splitting: {detail}")
        mid = max(1, len(batch) // 2)
        _upsert_location_chunk(client, url, batch[:mid], id_by_key)
        _upsert_location_chunk(client, url, batch[mid:], id_by_key)
        return
    if r.status_code == 400:
        key = batch[0].get("location_key") or "?"
        print(f"[push] skip location {key}: 400 {detail}")
        return
    print(f"[push] locations {r.status_code}: {detail}")
    r.raise_for_status()


def upsert_jobs(
    client: httpx.Client, base: str, job_rows: list[dict[str, Any]], chunk: int
) -> list[str]:
    by_id: dict[str, dict[str, Any]] = {}
    for row in job_rows:
        jid = row.get("id")
        if jid:
            by_id[str(jid)] = row
    rows = list(by_id.values())
    url = f"{base}/rest/v1/jobs?on_conflict=id"
    ok: list[str] = []
    for i in range(0, len(rows), chunk):
        ok.extend(_upsert_job_chunk(client, url, rows[i : i + chunk]))
        print(f"[push] jobs: {min(i + chunk, len(rows))}/{len(rows)}")
    return ok


def seed_analytics(
    client: httpx.Client, base: str, job_ids: list[str], chunk: int
) -> None:
    if not job_ids:
        return
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
        _raise_http(r, "job_analytics")
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
        _raise_http(r, "job_skills")
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
    _raise_http(r, "skills")
    rows = r.json() or []
    if rows:
        cache[key] = rows[0]["id"]
        return cache[key]
    r = client.post(
        f"{base}/rest/v1/skills?on_conflict=normalized_name",
        headers={"Prefer": "resolution=merge-duplicates,return=representation"},
        json=[{"name": key, "normalized_name": key, "last_seen": now}],
    )
    _raise_http(r, "skills")
    created = r.json() or []
    if created:
        cache[key] = created[0]["id"]
        return cache[key]
    # conflict may return empty — lookup again
    r = client.get(
        f"{base}/rest/v1/skills",
        params={"normalized_name": f"eq.{key}", "select": "id", "limit": "1"},
    )
    _raise_http(r, "skills")
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
        _raise_http(r, table)
        for row in r.json() or []:
            out[row[col]] = row["id"]


def _load_json(path: Path, fallback: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return fallback


def _upsert_job_chunk(
    client: httpx.Client, url: str, batch: list[dict[str, Any]]
) -> list[str]:
    """POST a jobs batch. On 400, split until the bad row can be skipped."""
    if not batch:
        return []
    r = client.post(
        url,
        headers={"Prefer": "resolution=merge-duplicates,return=minimal"},
        json=batch,
    )
    if r.is_success:
        return [str(row["id"]) for row in batch]
    detail = (r.text or "")[:1500]
    if r.status_code == 400 and len(batch) > 1:
        print(f"[push] jobs 400 on {len(batch)} rows, splitting: {detail}")
        mid = max(1, len(batch) // 2)
        return _upsert_job_chunk(client, url, batch[:mid]) + _upsert_job_chunk(
            client, url, batch[mid:]
        )
    if r.status_code == 400:
        jid = batch[0].get("id") or "?"
        print(f"[push] skip jobs {jid}: 400 {detail}")
        return []
    print(f"[push] jobs {r.status_code}: {detail}")
    r.raise_for_status()
    return []


def _raise_http(response: httpx.Response, label: str) -> None:
    if response.is_success:
        return
    print(f"[push] {label} {response.status_code}: {(response.text or '')[:1500]}")
    response.raise_for_status()


def _omit_none(row: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in row.items() if v is not None}


def _as_text(value: object, max_len: int) -> str | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, dict):
        return None
    if isinstance(value, (list, tuple)):
        parts = [_as_text(v, max_len) for v in value]
        joined = ", ".join(p for p in parts if p)
        return joined[:max_len] if joined else None
    s = str(value).strip()
    return s[:max_len] if s else None


def _coord(value: object, limit: float) -> float | None:
    if value is None or value == "":
        return None
    try:
        v = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if not math.isfinite(v) or abs(v) > limit:
        return None
    return v


def _enum_or_none(value: int | None, lo: int, hi: int) -> int | None:
    if value is None:
        return None
    return value if lo <= value <= hi else None


def _currency(value: object) -> str | None:
    s = re.sub(r"[^A-Za-z]", "", str(value or "")).upper()[:3]
    return s if len(s) == 3 else None


def _language(value: object) -> str | None:
    s = str(value or "").strip()
    return s[:10] if s else None


def _int4(n: object) -> int | None:
    """Jobs.salary_* are integer; JSON floats and overflow cause HTTP 400."""
    if n is None or n == "":
        return None
    try:
        v = float(n)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if not math.isfinite(v):
        return None
    iv = int(round(v))
    if iv < 0:
        return 0
    return min(iv, 2_147_483_647)


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


def _escape_id(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')
