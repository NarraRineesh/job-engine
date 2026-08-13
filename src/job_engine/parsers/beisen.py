from __future__ import annotations

from job_engine.parsers.base import BaseAtsParser


class BeisenParser(BaseAtsParser):
    ats = "beisen"

    def enrich_location(self, loc, row, description):
        # China-focused board
        if not loc.get("countryCode"):
            loc["countryCode"] = "CN"
            loc["country"] = "China"
