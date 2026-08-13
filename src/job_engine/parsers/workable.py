from __future__ import annotations

import json
import re
from typing import Any

from job_engine.parsers.base import BaseAtsParser
from job_engine.parsers.shared.employment import normalize_employment_type
from job_engine.parsers.shared.work_mode import normalize_work_mode


class WorkableParser(BaseAtsParser):
    ats = "workable"

    def enrich_employment_work(self, employment, work_mode, row, title, description):
        raw = row.get("raw")
        if isinstance(raw, str) and raw.startswith("{"):
            try:
                raw = json.loads(raw)
            except json.JSONDecodeError:
                raw = None
        if isinstance(raw, dict):
            if employment == "unknown" and raw.get("employment_type"):
                employment = normalize_employment_type(raw["employment_type"])
            tele = raw.get("telecommuting")
            if work_mode == "unknown" and tele is True:
                work_mode = "remote"
            loc = str(raw.get("location") or row.get("location") or "")
            if work_mode == "unknown":
                work_mode = normalize_work_mode(loc)
                if work_mode == "unknown" and re.search(r"remote|hybrid", loc, re.I):
                    work_mode = "hybrid" if "hybrid" in loc.lower() else "remote"
        return employment, work_mode
