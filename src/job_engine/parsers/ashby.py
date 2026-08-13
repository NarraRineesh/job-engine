"""Ashby-specific parsing."""

from __future__ import annotations

import json
import re
from typing import Any

from job_engine.parsers.base import BaseAtsParser
from job_engine.parsers.shared.employment import normalize_employment_type
from job_engine.parsers.shared.work_mode import normalize_work_mode


class AshbyParser(BaseAtsParser):
    ats = "ashby"

    def enrich_employment_work(
        self,
        employment: str,
        work_mode: str,
        row: dict[str, Any],
        title: str,
        description: str,
    ) -> tuple[str, str]:
        raw = row.get("raw")
        if isinstance(raw, str) and raw.startswith("{"):
            try:
                raw = json.loads(raw)
            except json.JSONDecodeError:
                raw = None
        if isinstance(raw, dict):
            et = raw.get("employmentType") or raw.get("employment_type")
            if et and employment == "unknown":
                employment = normalize_employment_type(et)
            wm = raw.get("workplaceType") or raw.get("workplace_type")
            if wm and work_mode == "unknown":
                work_mode = normalize_work_mode(wm)
                if work_mode == "unknown":
                    s = str(wm).lower()
                    if "hybrid" in s:
                        work_mode = "hybrid"
                    elif "remote" in s:
                        work_mode = "remote"
                    elif "office" in s or "onsite" in s:
                        work_mode = "onsite"
        if work_mode == "unknown" and re.search(r"Remote\s*-\s*", str(row.get("location") or ""), re.I):
            work_mode = "remote"
        return employment, work_mode
