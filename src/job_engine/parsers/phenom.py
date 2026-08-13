from __future__ import annotations

import re

from job_engine.parsers.base import BaseAtsParser


class PhenomParser(BaseAtsParser):
    ats = "phenom"

    def enrich_location(self, loc, row, description):
        if not loc.get("countryCode") and loc.get("formatted"):
            # Phenom often "City, Country"
            parts = [p.strip() for p in loc["formatted"].split(",")]
            if parts and parts[-1].lower() in {"india", "in"}:
                loc["countryCode"] = "IN"
                loc["country"] = "India"

    def enrich_employment_work(self, employment, work_mode, row, title, description):
        if work_mode == "unknown" and re.search(r"work from home|remote", title + description[:1500], re.I):
            work_mode = "remote"
        return employment, work_mode
