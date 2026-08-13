"""Seek — AU/NZ board; salary often in summary."""

from __future__ import annotations

from typing import Any

from job_engine.parsers.base import BaseAtsParser
from job_engine.parsers.shared.salary import parse_salary


class SeekParser(BaseAtsParser):
    ats = "seek"

    def enrich_employment_work(
        self,
        employment: str,
        work_mode: str,
        row: dict[str, Any],
        title: str,
        description: str,
    ) -> tuple[str, str]:
        summary = row.get("salary_summary") or ""
        if summary and not row.get("salary_min"):
            # ensure parse runs via base; nothing else
            pass
        # Seek work types often in commitment
        commitment = str(row.get("commitment") or "").lower()
        if employment == "unknown" and commitment:
            from job_engine.parsers.shared.employment import normalize_employment_type

            employment = normalize_employment_type(commitment)
        if work_mode == "unknown" and "work from home" in (description or "").lower()[:2000]:
            work_mode = "remote"
        return employment, work_mode

    def enrich_location(self, loc: dict[str, Any], row: dict[str, Any], description: str) -> None:
        if not loc.get("countryCode"):
            fmt = (loc.get("formatted") or "").lower()
            if any(x in fmt for x in ("australia", "sydney", "melbourne", "brisbane", "perth")):
                loc["countryCode"] = "AU"
                loc["country"] = "Australia"
            elif any(x in fmt for x in ("new zealand", "auckland", "wellington")):
                loc["countryCode"] = "NZ"
                loc["country"] = "New Zealand"
        # force salary from summary if missing
        if row.get("salary_summary") and not row.get("_seek_salary_done"):
            parsed = parse_salary(row.get("salary_summary"))
            row["_seek_salary_parsed"] = parsed
