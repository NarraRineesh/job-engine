"""Greenhouse-specific parsing."""

from __future__ import annotations

import json
import re
from typing import Any

from job_engine.parsers.base import BaseAtsParser
from job_engine.parsers.shared.employment import normalize_employment_type


class GreenhouseParser(BaseAtsParser):
    ats = "greenhouse"

    def enrich_employment_work(
        self,
        employment: str,
        work_mode: str,
        row: dict[str, Any],
        title: str,
        description: str,
    ) -> tuple[str, str]:
        raw = row.get("raw")
        if isinstance(raw, str) and raw.strip().startswith("{"):
            try:
                raw = json.loads(raw)
            except json.JSONDecodeError:
                raw = None
        if isinstance(raw, dict):
            for key in ("employment_type", "employmentType", "type"):
                if raw.get(key) and employment == "unknown":
                    employment = normalize_employment_type(raw[key])
            metadata = raw.get("metadata") or []
            if isinstance(metadata, list):
                for item in metadata:
                    if not isinstance(item, dict):
                        continue
                    name = str(item.get("name") or "").lower()
                    val = item.get("value")
                    if "employment" in name and employment == "unknown":
                        employment = normalize_employment_type(val)
                    if "remote" in name and work_mode == "unknown":
                        if str(val).lower() in {"true", "yes", "remote"}:
                            work_mode = "remote"
        # Greenhouse often puts "Remote - US" in location/title already handled
        if work_mode == "unknown" and re.search(r"\bremote\b", title, re.I):
            work_mode = "remote"
        return employment, work_mode
