from __future__ import annotations

import json

from job_engine.parsers.base import BaseAtsParser
from job_engine.parsers.shared.employment import normalize_employment_type
from job_engine.parsers.shared.work_mode import normalize_work_mode


class SmartRecruitersParser(BaseAtsParser):
    ats = "smartrecruiters"

    def enrich_employment_work(self, employment, work_mode, row, title, description):
        raw = row.get("raw")
        if isinstance(raw, str) and raw.startswith("{"):
            try:
                raw = json.loads(raw)
            except json.JSONDecodeError:
                raw = None
        if isinstance(raw, dict):
            typeref = raw.get("typeOfEmployment") or {}
            if employment == "unknown" and isinstance(typeref, dict):
                employment = normalize_employment_type(typeref.get("label") or typeref.get("id"))
            loc = raw.get("location") or {}
            if work_mode == "unknown" and isinstance(loc, dict) and loc.get("remote"):
                work_mode = "remote"
            if work_mode == "unknown" and raw.get("location"):
                work_mode = normalize_work_mode(str(raw.get("location")))
        return employment, work_mode
