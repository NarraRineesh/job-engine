"""Salary parsing including INR / LPA / lakh / crore."""

from __future__ import annotations

import re
from typing import Any

CURRENCY_MAP = {
    "$": "USD",
    "US$": "USD",
    "CA$": "CAD",
    "A$": "AUD",
    "NZ$": "NZD",
    "HK$": "HKD",
    "S$": "SGD",
    "R$": "BRL",
    "£": "GBP",
    "€": "EUR",
    "¥": "JPY",
    "₹": "INR",
    "INR": "INR",
    "USD": "USD",
    "EUR": "EUR",
    "GBP": "GBP",
    "CAD": "CAD",
    "AUD": "AUD",
    "LPA": "INR",
    "CTC": "INR",
}

_SALARY_RANGE_RE = re.compile(
    r"([$£€¥₹]|CA\$|US\$|A\$|NZ\$|HK\$|S\$|R\$|INR|USD|EUR|GBP|CTC|LPA)?"
    r"\s*(\d[\d,. ]*)\s*(K|M|k|m|thousand|million|lakh|L|cr|crore|LPA)?"
    r"\s*(?:[-–—~]|to)\s*"
    r"([$£€¥₹]|CA\$|US\$|A\$|NZ\$|HK\$|S\$|R\$|INR|USD|EUR|GBP|CTC|LPA)?"
    r"\s*(\d[\d,. ]*)\s*(K|M|k|m|thousand|million|lakh|L|cr|crore|LPA)?",
    re.I,
)

_SALARY_SINGLE_RE = re.compile(
    r"([$£€¥₹]|CA\$|US\$|A\$|INR|USD|EUR|GBP|CTC|LPA)?"
    r"\s*(\d[\d,. ]{2,})\s*(K|M|k|m|thousand|million|lakh|L|cr|crore|LPA)?",
    re.I,
)

_LPA_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*[-–—to]+\s*(\d+(?:\.\d+)?)\s*(?:LPA|lpa|lakhs?\s*p\.?a\.?)",
    re.I,
)


def _token(num: str, unit: str | None) -> float | None:
    cleaned = str(num or "").replace(",", "").replace(" ", "").rstrip(".")
    if not cleaned or cleaned.count(".") > 1:
        return None
    try:
        value = float(cleaned)
    except ValueError:
        return None
    multiplier = 1.0
    if unit:
        u = unit.lower()
        if u in {"lakh", "l"} or u == "lpa":
            multiplier = 100_000.0
        elif u.startswith("k") or u == "thousand":
            multiplier = 1_000.0
        elif u in {"cr", "crore"}:
            multiplier = 10_000_000.0
        elif u.startswith("m") or u == "million":
            multiplier = 1_000_000.0
    return value * multiplier


def empty_salary() -> dict[str, Any]:
    return {"currency": None, "min": None, "max": None, "period": None}


def parse_salary(text: object) -> dict[str, Any]:
    salary = empty_salary()
    raw = str(text or "").strip()
    if not raw:
        return salary

    lpa = _LPA_RE.search(raw)
    if lpa:
        lo = _token(lpa.group(1), "lakh")
        hi = _token(lpa.group(2), "lakh")
        salary["currency"] = "INR"
        salary["min"], salary["max"] = lo, hi
        salary["period"] = "year"
        return salary

    m = _SALARY_RANGE_RE.search(raw)
    if m:
        ckey = m.group(1) or m.group(4) or ""
        salary["currency"] = (
            CURRENCY_MAP.get(ckey) or CURRENCY_MAP.get(ckey.upper()) or None
        )
        lo = _token(m.group(2), m.group(3))
        hi = _token(m.group(5), m.group(6))
        if lo is not None and hi is not None and lo > hi:
            lo, hi = hi, lo
        # LPA unit on either side
        if (m.group(3) or m.group(6) or "").lower() == "lpa":
            salary["currency"] = salary["currency"] or "INR"
        salary["min"], salary["max"] = lo, hi
    else:
        m2 = _SALARY_SINGLE_RE.search(raw)
        if m2:
            ckey = m2.group(1) or ""
            salary["currency"] = (
                CURRENCY_MAP.get(ckey) or CURRENCY_MAP.get(ckey.upper()) or None
            )
            val = _token(m2.group(2), m2.group(3))
            salary["min"] = salary["max"] = val

    lower = raw.lower()
    if re.search(r"\bhour(ly)?\b", lower):
        salary["period"] = "hour"
    elif re.search(r"\bmonth(ly)?\b", lower):
        salary["period"] = "month"
    elif re.search(r"\bweek(ly)?\b", lower):
        salary["period"] = "week"
    elif re.search(r"\bday\b|daily\b", lower):
        salary["period"] = "day"
    elif salary["min"] is not None or salary["max"] is not None:
        salary["period"] = "year"
    if "lpa" in lower or "ctc" in lower:
        salary["currency"] = salary["currency"] or "INR"
        salary["period"] = "year"
    return salary
