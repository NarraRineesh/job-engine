"""Keka — India-heavy SMB ATS public career boards."""

from __future__ import annotations

import json
import re
from typing import Any

from job_engine.parsers.base import BaseAtsParser
from job_engine.parsers.shared.employment import normalize_employment_type
from job_engine.parsers.shared.experience import parse_experience
from job_engine.parsers.shared.location import INDIAN_CITIES, compact_key
from job_engine.parsers.shared.salary import parse_salary
from job_engine.schema import Experience, NestedJob, Salary


class KekaParser(BaseAtsParser):
    ats = "keka"

    def parse_row(self, row: dict[str, Any], *, company_slug_hint: str | None = None) -> NestedJob:
        job = super().parse_row(row, company_slug_hint=company_slug_hint)
        raw = _raw_dict(row)
        updates: dict[str, Any] = {}

        if isinstance(raw, dict):
            exp_text = raw.get("experience")
            if exp_text and (job.experience.min is None or job.experience.max == job.experience.min):
                mn, mx = parse_experience(str(exp_text))
                if mn is None and mx is None:
                    m = re.search(r"(\d+)\s*[-–to]+\s*(\d+)", str(exp_text), re.I)
                    if m:
                        mn, mx = int(m.group(1)), int(m.group(2))
                if mn is not None or mx is not None:
                    updates["experience"] = Experience(
                        min=mn, max=mx if mx is not None else mn
                    )

            salary = job.salary.model_dump()
            if salary.get("min") is None and salary.get("max") is None:
                fmt = raw.get("salaryRangeFormat")
                if isinstance(fmt, str) and fmt.strip():
                    filled = parse_salary(fmt)
                    for key in ("currency", "min", "max", "period"):
                        if salary.get(key) is None and filled.get(key) is not None:
                            salary[key] = filled[key]
                    updates["salary"] = Salary(**salary)

        if updates:
            return job.model_copy(update=updates)
        return job

    def enrich_location(self, loc: dict[str, Any], row: dict[str, Any], description: str) -> None:
        raw = _raw_dict(row)
        locations = raw.get("jobLocations") if isinstance(raw, dict) else None
        if isinstance(locations, list):
            for item in locations:
                if not isinstance(item, dict):
                    continue
                city = str(item.get("city") or "").strip()
                state = str(item.get("state") or item.get("name") or "").strip()
                country = str(item.get("countryName") or "").strip()
                code = str(item.get("countryCode") or "").strip().upper()
                if city and not loc.get("city"):
                    loc["city"] = city
                if state and not loc.get("state"):
                    loc["state"] = state
                if country and not loc.get("country"):
                    loc["country"] = country
                if code and not loc.get("countryCode"):
                    loc["countryCode"] = code
                break

        if not loc.get("countryCode"):
            fmt = (loc.get("formatted") or "").lower()
            for key, hit in INDIAN_CITIES.items():
                if key in compact_key(fmt) or hit["city"].lower() in fmt:
                    loc["city"] = loc.get("city") or hit["city"]
                    loc["state"] = loc.get("state") or hit["state"]
                    loc["countryCode"] = "IN"
                    loc["country"] = "India"
                    break
            if "india" in fmt:
                loc["countryCode"] = "IN"
                loc["country"] = "India"

    def enrich_employment_work(
        self,
        employment: str,
        work_mode: str,
        row: dict[str, Any],
        title: str,
        description: str,
    ) -> tuple[str, str]:
        raw = _raw_dict(row)
        if employment == "unknown" and isinstance(raw, dict):
            jt = raw.get("jobType")
            if jt == 1:
                employment = "part_time"
            elif jt == 2:
                employment = "full_time"
            elif jt is not None:
                employment = normalize_employment_type(jt)
        return employment, work_mode

    def enrich_skills(
        self, skills: dict[str, list[str]], row: dict[str, Any], description: str
    ) -> dict[str, list[str]]:
        raw = _raw_dict(row)
        names = raw.get("skillNames") if isinstance(raw, dict) else None
        if isinstance(names, list):
            required = list(skills.get("required") or [])
            seen = {s.lower() for s in required}
            for name in names:
                text = re.sub(r"\s+", " ", str(name or "").strip().lower())
                if text and text not in seen:
                    required.append(text)
                    seen.add(text)
            skills = {**skills, "required": required}
        return skills


def _raw_dict(row: dict[str, Any]) -> dict[str, Any] | None:
    raw = row.get("raw")
    if isinstance(raw, str) and raw.strip().startswith("{"):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return None
    return raw if isinstance(raw, dict) else None
