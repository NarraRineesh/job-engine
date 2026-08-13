"""Work mode inference from structured flags + text."""

from __future__ import annotations

import re

_VALID = {"remote", "hybrid", "onsite", "unknown"}


def normalize_work_mode(raw: object) -> str:
    if raw is None or raw == "":
        return "unknown"
    s = str(raw).strip().lower().replace("-", "_").replace(" ", "_")
    if s in _VALID:
        return s
    if s in {"work_from_home", "wfh", "telework", "anywhere"}:
        return "remote"
    if s in {"office", "in_office", "on_site", "in-office"}:
        return "onsite"
    return "unknown"


def infer_work_mode(
    *,
    is_remote: bool | None = None,
    location: str = "",
    title: str = "",
    description: str = "",
) -> str:
    if is_remote is True:
        return "remote"
    hay = f"{title} {location} {description[:3000]}".lower()
    if re.search(r"\bhybrid\b", hay):
        return "hybrid"
    if re.search(
        r"\bremote\b|\bwfh\b|work from home|\banywhere\b|\btelework\b|work-from-home",
        hay,
    ):
        return "remote"
    if re.search(r"\bonsite\b|\bon-site\b|\bin-office\b|\bin office\b", hay):
        return "onsite"
    return "unknown"
