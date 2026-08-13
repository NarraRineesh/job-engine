"""Base ATS parser: structured fields first, then shared regex gaps."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from job_engine.companies import resolve_slug
from job_engine.parsers.shared.employment import (
    infer_employment_from_text,
    normalize_employment_type,
)
from job_engine.parsers.shared.experience import parse_experience
from job_engine.parsers.shared.location import parse_location
from job_engine.parsers.shared.salary import parse_salary
from job_engine.parsers.shared.skills import extract_skills
from job_engine.parsers.shared.work_mode import infer_work_mode
from job_engine.schema import NestedJob


def _title_tokens(title: str) -> list[str]:
    return [t for t in re.split(r"[^a-z0-9+#]+", title.lower()) if t]


def _truthy_remote(val: object) -> bool | None:
    if val is None or val == "":
        return None
    if isinstance(val, bool):
        return val
    s = str(val).strip().lower()
    if s in {"true", "1", "yes"}:
        return True
    if s in {"false", "0", "no"}:
        return False
    return None


class BaseAtsParser:
    """Default parser used for any ATS; subclasses override hooks."""

    ats: str = "custom"

    def parse_row(self, row: dict[str, Any], *, company_slug_hint: str | None = None) -> NestedJob:
        ats = (row.get("ats_type") or row.get("ats") or self.ats or "custom").strip().lower()
        company_name = (row.get("company") or "").strip() or "Unknown"
        external_id = str(row.get("ats_id") or row.get("externalId") or "").strip()
        slug = resolve_slug(ats, company_name, company_slug_hint)
        if not external_id:
            external_id = re.sub(r"[^a-zA-Z0-9_-]+", "-", (row.get("url") or "")[-40:]) or "unknown"

        title = (row.get("title") or "").strip() or "Untitled"
        description = (row.get("description") or "") or ""
        location_fmt = (row.get("location") or "").strip()
        apply_url = (row.get("apply_url") or row.get("url") or "").strip()
        url = (row.get("url") or apply_url).strip()

        # structured
        employment = normalize_employment_type(row.get("employment_type"))
        if employment == "unknown":
            employment = infer_employment_from_text(title, description)

        is_remote = _truthy_remote(row.get("is_remote"))
        work_mode = infer_work_mode(
            is_remote=is_remote,
            location=location_fmt,
            title=title,
            description=description,
        )

        loc = parse_location(location_fmt, row.get("country_iso") or None)
        self.enrich_location(loc, row, description)

        salary = {
            "currency": (row.get("salary_currency") or None) or None,
            "min": _float(row.get("salary_min")),
            "max": _float(row.get("salary_max")),
            "period": _period(row.get("salary_period")),
        }
        if salary["min"] is None and salary["max"] is None:
            parsed = parse_salary(row.get("salary_summary") or description[:2000])
            salary = {**salary, **{k: v for k, v in parsed.items() if v is not None}}
        elif not salary["currency"] and row.get("salary_summary"):
            parsed = parse_salary(row.get("salary_summary"))
            salary["currency"] = parsed.get("currency") or salary["currency"]
            salary["period"] = salary["period"] or parsed.get("period")

        exp_min = _int(row.get("experience"))
        exp_max = exp_min
        if exp_min is None:
            exp_min, exp_max = parse_experience(f"{title}\n{description[:5000]}")

        skills = extract_skills(description, title)
        skills = self.enrich_skills(skills, row, description)

        department = (row.get("department") or None) or None
        team = (row.get("team") or None) or None
        department, team = self.enrich_department_team(department, team, row, description)

        employment, work_mode = self.enrich_employment_work(
            employment, work_mode, row, title, description
        )

        posted = str(row.get("posted_at") or "").strip()
        scraped = str(row.get("fetched_at") or row.get("scrapedAt") or "").strip()
        if not scraped:
            scraped = datetime.now(UTC).isoformat()

        job_id = f"{ats}:{slug}:{external_id}"
        return NestedJob(
            id=job_id,
            source={
                "ats": ats,
                "companySlug": slug,
                "externalId": external_id,
                "applyUrl": apply_url or url,
                "detailApiUrl": url if url != apply_url else "",
            },
            company={"id": f"{ats}:{slug}", "name": company_name, "slug": slug},
            title=title,
            titleTokens=_title_tokens(title),
            department=department,
            team=team,
            employmentType=employment if employment in {
                "full_time", "part_time", "contract", "intern", "temporary", "freelance", "unknown"
            } else "unknown",
            workMode=work_mode if work_mode in {"remote", "hybrid", "onsite", "unknown"} else "unknown",
            experience={"min": exp_min, "max": exp_max},
            salary=salary,
            location=loc,
            skills=skills,
            description=description or None,
            postedAt=posted,
            updatedAt=posted or scraped,
            scrapedAt=scraped,
            status="active",
        )

    # --- hooks for per-ATS subclasses ---

    def enrich_location(self, loc: dict[str, Any], row: dict[str, Any], description: str) -> None:
        return None

    def enrich_skills(
        self, skills: dict[str, list[str]], row: dict[str, Any], description: str
    ) -> dict[str, list[str]]:
        return skills

    def enrich_department_team(
        self,
        department: str | None,
        team: str | None,
        row: dict[str, Any],
        description: str,
    ) -> tuple[str | None, str | None]:
        return department, team

    def enrich_employment_work(
        self,
        employment: str,
        work_mode: str,
        row: dict[str, Any],
        title: str,
        description: str,
    ) -> tuple[str, str]:
        return employment, work_mode


def _float(v: object) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _int(v: object) -> int | None:
    if v is None or v == "":
        return None
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def _period(v: object) -> str | None:
    if v is None or v == "":
        return None
    s = str(v).strip().lower()
    # ats-scrapers uses HOUR/MONTH/YEAR
    s = s.replace("yearly", "year").replace("annual", "year").replace("monthly", "month")
    s = s.replace("hourly", "hour")
    if s.isupper() or s.upper() == s:
        s = s.lower()
    mapping = {
        "hour": "hour",
        "day": "day",
        "week": "week",
        "month": "month",
        "year": "year",
    }
    return mapping.get(s)
