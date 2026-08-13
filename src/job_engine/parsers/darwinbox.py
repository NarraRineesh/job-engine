"""Darwinbox — India-heavy ATS."""

from __future__ import annotations

from typing import Any

from job_engine.parsers.base import BaseAtsParser
from job_engine.parsers.shared.location import INDIAN_CITIES, compact_key


class DarwinboxParser(BaseAtsParser):
    ats = "darwinbox"

    def enrich_location(self, loc: dict[str, Any], row: dict[str, Any], description: str) -> None:
        # Prefer India when city matches and country missing
        if not loc.get("countryCode"):
            fmt = (loc.get("formatted") or "").lower()
            for key, hit in INDIAN_CITIES.items():
                if key in compact_key(fmt) or hit["city"].lower() in fmt:
                    loc["city"] = hit["city"]
                    loc["state"] = hit["state"]
                    loc["countryCode"] = "IN"
                    loc["country"] = "India"
                    break
            if "india" in fmt:
                loc["countryCode"] = "IN"
                loc["country"] = "India"
