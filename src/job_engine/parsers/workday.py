from __future__ import annotations

import json
import re
from typing import Any

from job_engine.parsers.base import BaseAtsParser
from job_engine.parsers.shared.employment import normalize_employment_type


class WorkdayParser(BaseAtsParser):
    ats = "workday"

    def enrich_employment_work(self, employment, work_mode, row, title, description):
        raw = row.get("raw")
        if isinstance(raw, str) and raw.startswith("{"):
            try:
                raw = json.loads(raw)
            except json.JSONDecodeError:
                raw = None
        if isinstance(raw, dict) and employment == "unknown":
            for key in ("timeType", "employmentType", "workerSubType"):
                node = raw.get(key)
                if isinstance(node, dict):
                    employment = normalize_employment_type(node.get("descriptor") or node.get("id"))
                elif node:
                    employment = normalize_employment_type(node)
                if employment != "unknown":
                    break
        if work_mode == "unknown" and re.search(r"\bhybrid\b|\bremote\b", description[:3000], re.I):
            work_mode = "hybrid" if re.search(r"\bhybrid\b", description[:3000], re.I) else "remote"
        return employment, work_mode
