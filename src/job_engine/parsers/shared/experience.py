"""Years-of-experience extraction."""

from __future__ import annotations

import re

_RANGE = re.compile(
    r"(\d{1,2})\s*(?:\+|plus)?\s*[-–—to]+\s*(\d{1,2})\s*\+?\s*"
    r"(?:years?|yrs?|y\.?o\.?e\.?)",
    re.I,
)
_SINGLE = re.compile(
    r"(?:(?:min(?:imum)?|at\s+least|over|more\s+than)\s+)?"
    r"(\d{1,2})\s*\+?\s*(?:years?|yrs?|y\.?o\.?e\.?)"
    r"(?:\s+of\s+experience)?",
    re.I,
)
_FRESHER = re.compile(r"\b(?:fresher|entry[\s-]?level|no\s+experience|0\s*[-–]?\s*1\s*years?)\b", re.I)


def clamp_years(n: object) -> int | None:
    if n is None or n == "":
        return None
    try:
        v = int(float(n))
    except (TypeError, ValueError):
        return None
    if v < 0:
        return None
    if v == 0:
        return 0
    return min(50, v)


def parse_experience(text: str) -> tuple[int | None, int | None]:
    raw = str(text or "")
    if not raw.strip():
        return None, None
    if _FRESHER.search(raw):
        return 0, 1
    m = _RANGE.search(raw)
    if m:
        lo, hi = clamp_years(m.group(1)), clamp_years(m.group(2))
        if lo is not None and hi is not None and lo > hi:
            lo, hi = hi, lo
        return lo, hi
    m = _SINGLE.search(raw)
    if m:
        y = clamp_years(m.group(1))
        if y is None:
            return None, None
        # "5+ years" → min=5
        if "+" in m.group(0) or "plus" in m.group(0).lower():
            return y, None
        return y, y
    return None, None
