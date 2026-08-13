"""Employment type normalization + regex."""

from __future__ import annotations

import re

_VALID = {
    "full_time",
    "part_time",
    "contract",
    "intern",
    "temporary",
    "freelance",
    "unknown",
}

# Map ats-scrapers UPPER enums
_ATS_MAP = {
    "FULL_TIME": "full_time",
    "PART_TIME": "part_time",
    "CONTRACT": "contract",
    "INTERN": "intern",
    "TEMPORARY": "temporary",
}


def normalize_employment_type(raw: object) -> str:
    if raw is None or raw == "":
        return "unknown"
    s = str(raw).strip()
    if s in _ATS_MAP:
        return _ATS_MAP[s]
    key = s.lower().replace("-", "_").replace(" ", "_")
    if key in _VALID:
        return key
    if re.search(r"full[_\s]?time|permanent|cdi|exempt", key):
        return "full_time"
    if re.search(r"part[_\s]?time", key):
        return "part_time"
    if re.search(r"contract|contractor|freelance|cdd|consultant|contingent", key):
        return "contract"
    if re.search(r"intern|internship|trainee|apprentice", key):
        return "intern"
    if re.search(r"temp|temporary|seasonal", key):
        return "temporary"
    return "unknown"


def infer_employment_from_text(title: str = "", description: str = "") -> str:
    hay = f"{title}\n{description[:4000]}".lower()
    return normalize_employment_type(hay)
