from __future__ import annotations

import re

from job_engine.parsers.base import BaseAtsParser
from job_engine.parsers.shared.employment import normalize_employment_type


class AmazonParser(BaseAtsParser):
    ats = "amazon"

    def enrich_employment_work(self, employment, work_mode, row, title, description):
        if employment == "unknown":
            if re.search(r"\bintern\b", title, re.I):
                employment = "intern"
            else:
                employment = normalize_employment_type(row.get("commitment") or "full_time")
                if employment == "unknown":
                    employment = "full_time"
        if work_mode == "unknown" and re.search(r"\bvirtual\b|\bremote\b", title, re.I):
            work_mode = "remote"
        return employment, work_mode
