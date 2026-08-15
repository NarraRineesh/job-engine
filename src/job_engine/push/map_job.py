"""Map scraped job dicts to nested company / location / job rows."""

from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import UTC, datetime
from typing import Any

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
