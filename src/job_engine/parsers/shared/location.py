"""Location parsing with India city/state awareness."""

from __future__ import annotations

import re
from typing import Any

COUNTRY_NAME_TO_ISO = {
    "india": "IN",
    "bharat": "IN",
    "united states": "US",
    "usa": "US",
    "us": "US",
    "united kingdom": "GB",
    "uk": "GB",
    "canada": "CA",
    "australia": "AU",
    "germany": "DE",
    "france": "FR",
    "singapore": "SG",
    "united arab emirates": "AE",
    "uae": "AE",
    "ireland": "IE",
    "japan": "JP",
    "china": "CN",
    "brazil": "BR",
    "mexico": "MX",
    "poland": "PL",
    "spain": "ES",
    "netherlands": "NL",
}

ISO_TO_COUNTRY = {
    "IN": "India",
    "US": "United States",
    "GB": "United Kingdom",
    "CA": "Canada",
    "AU": "Australia",
    "DE": "Germany",
    "FR": "France",
    "SG": "Singapore",
    "AE": "United Arab Emirates",
    "IE": "Ireland",
    "JP": "Japan",
    "CN": "China",
    "BR": "Brazil",
    "MX": "Mexico",
    "PL": "Poland",
    "ES": "Spain",
    "NL": "Netherlands",
}

INDIAN_STATES = {
    "andhrapradesh": "Andhra Pradesh",
    "karnataka": "Karnataka",
    "kerala": "Kerala",
    "maharashtra": "Maharashtra",
    "tamilnadu": "Tamil Nadu",
    "telangana": "Telangana",
    "uttarpradesh": "Uttar Pradesh",
    "westbengal": "West Bengal",
    "gujarat": "Gujarat",
    "rajasthan": "Rajasthan",
    "delhi": "Delhi",
    "haryana": "Haryana",
    "punjab": "Punjab",
    "madhyapradesh": "Madhya Pradesh",
    "bihar": "Bihar",
    "odisha": "Odisha",
    "orissa": "Odisha",
    "jharkhand": "Jharkhand",
    "chhattisgarh": "Chhattisgarh",
    "assam": "Assam",
    "uttarakhand": "Uttarakhand",
    "goa": "Goa",
    "chandigarh": "Chandigarh",
    "puducherry": "Puducherry",
    "jammuandkashmir": "Jammu and Kashmir",
    "ladakh": "Ladakh",
}

INDIAN_CITIES = {
    "bengaluru": {"city": "Bengaluru", "state": "Karnataka"},
    "bangalore": {"city": "Bengaluru", "state": "Karnataka"},
    "mumbai": {"city": "Mumbai", "state": "Maharashtra"},
    "pune": {"city": "Pune", "state": "Maharashtra"},
    "hyderabad": {"city": "Hyderabad", "state": "Telangana"},
    "chennai": {"city": "Chennai", "state": "Tamil Nadu"},
    "delhi": {"city": "Delhi", "state": "Delhi"},
    "newdelhi": {"city": "New Delhi", "state": "Delhi"},
    "gurgaon": {"city": "Gurugram", "state": "Haryana"},
    "gurugram": {"city": "Gurugram", "state": "Haryana"},
    "noida": {"city": "Noida", "state": "Uttar Pradesh"},
    "kolkata": {"city": "Kolkata", "state": "West Bengal"},
    "ahmedabad": {"city": "Ahmedabad", "state": "Gujarat"},
    "jaipur": {"city": "Jaipur", "state": "Rajasthan"},
    "chandigarh": {"city": "Chandigarh", "state": "Chandigarh"},
    "kochi": {"city": "Kochi", "state": "Kerala"},
    "cochin": {"city": "Kochi", "state": "Kerala"},
    "indore": {"city": "Indore", "state": "Madhya Pradesh"},
    "coimbatore": {"city": "Coimbatore", "state": "Tamil Nadu"},
    "visakhapatnam": {"city": "Visakhapatnam", "state": "Andhra Pradesh"},
    "vizag": {"city": "Visakhapatnam", "state": "Andhra Pradesh"},
}

US_STATE_CODES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID", "IL",
    "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT",
    "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI",
    "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY", "DC",
}


def compact_key(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def empty_location(formatted: str = "") -> dict[str, Any]:
    return {
        "formatted": formatted or "",
        "countryCode": None,
        "country": None,
        "state": None,
        "city": None,
    }


def parse_location(formatted: object, country_iso: str | None = None) -> dict[str, Any]:
    raw = str(formatted or "").strip()
    loc = empty_location(raw)
    if country_iso:
        code = country_iso.strip().upper()
        loc["countryCode"] = code
        loc["country"] = ISO_TO_COUNTRY.get(code)
    if not raw:
        return loc

    parts = [p.strip() for p in re.split(r"[,|/•·]+", raw) if p.strip()]

    if len(parts) >= 2:
        maybe_state = parts[-1].upper()
        if re.fullmatch(r"[A-Z]{2}", maybe_state) and maybe_state in US_STATE_CODES:
            loc["countryCode"] = "US"
            loc["country"] = "United States"
            loc["state"] = maybe_state
            loc["city"] = parts[0]
            return loc

    for part in parts:
        compact = compact_key(part)
        code = COUNTRY_NAME_TO_ISO.get(part.lower()) or COUNTRY_NAME_TO_ISO.get(compact)
        if code:
            loc["countryCode"] = code
            loc["country"] = ISO_TO_COUNTRY.get(code, part)
            break

    for part in parts:
        hit = INDIAN_CITIES.get(compact_key(part))
        if hit:
            loc["city"] = hit["city"]
            loc["state"] = hit["state"]
            if not loc["countryCode"]:
                loc["countryCode"] = "IN"
                loc["country"] = "India"
            break

    if not loc["state"]:
        for part in parts:
            state = INDIAN_STATES.get(compact_key(part))
            if state:
                loc["state"] = state
                if not loc["countryCode"]:
                    loc["countryCode"] = "IN"
                    loc["country"] = "India"
                break

    if not loc["city"] and parts:
        first = parts[0]
        if not COUNTRY_NAME_TO_ISO.get(compact_key(first)) and not INDIAN_STATES.get(
            compact_key(first)
        ):
            loc["city"] = first

    return loc


def matches_country(loc: dict[str, Any] | None, country: str) -> bool:
    """True if location belongs to ``country`` (ISO-2 or common name).

    Checks countryCode, country name, state, city, and formatted text.
    For ``IN``, also matches Indian city/state lexicons. Avoids treating
    US Indiana (``state=IN`` / ``Indianapolis, IN``) as India.
    """
    wanted = _normalize_country_filter(country)
    if not wanted:
        return True
    loc = loc if isinstance(loc, dict) else {}

    code = str(loc.get("countryCode") or "").strip().upper()
    if code == wanted:
        return True

    # Explicit other country → no match (e.g. US job vs --country IN)
    if code and code != wanted:
        return False

    name = str(loc.get("country") or "").strip()
    if name:
        mapped = COUNTRY_NAME_TO_ISO.get(name.lower()) or COUNTRY_NAME_TO_ISO.get(
            compact_key(name)
        )
        if mapped == wanted:
            return True
        if mapped and mapped != wanted:
            return False
        if ISO_TO_COUNTRY.get(wanted, "").lower() == name.lower():
            return True

    city = str(loc.get("city") or "").strip()
    state = str(loc.get("state") or "").strip()
    formatted = str(loc.get("formatted") or "").strip()
    blob = " ".join(p for p in (formatted, city, state, name) if p)
    if not blob:
        return False

    # Country name / aliases in free text
    for alias, iso in COUNTRY_NAME_TO_ISO.items():
        if iso != wanted or len(alias) < 3:
            continue
        if re.search(rf"\b{re.escape(alias)}\b", blob, re.I):
            return True
    official = ISO_TO_COUNTRY.get(wanted)
    if official and re.search(rf"\b{re.escape(official)}\b", blob, re.I):
        return True

    if wanted == "IN":
        return _looks_like_india(city=city, state=state, formatted=formatted, blob=blob)

    if wanted == "US":
        # City, ST pattern already sets countryCode=US in parse_location;
        # also accept bare US state codes when country is unset.
        if state.upper() in US_STATE_CODES and state.upper() != "IN":
            return True
        if re.search(r"\b(usa|u\.s\.a\.|united states)\b", blob, re.I):
            return True

    return False


def _normalize_country_filter(country: str) -> str:
    raw = str(country or "").strip()
    if not raw:
        return ""
    if len(raw) == 2:
        return raw.upper()
    return (
        COUNTRY_NAME_TO_ISO.get(raw.lower())
        or COUNTRY_NAME_TO_ISO.get(compact_key(raw))
        or raw.upper()
    )


def _looks_like_india(
    *, city: str, state: str, formatted: str, blob: str
) -> bool:
    # US Indiana: "Indianapolis, IN" / state code IN without India signals
    if re.search(r"\bindianapolis\b", blob, re.I):
        return False
    if state.upper() == "IN" and not (
        INDIAN_CITIES.get(compact_key(city))
        or INDIAN_STATES.get(compact_key(state))
        or re.search(r"\b(india|bharat)\b", blob, re.I)
    ):
        # bare "IN" state with no India lexicon hit → Indiana, not India
        if not city or compact_key(city) not in INDIAN_CITIES:
            parts = [p.strip() for p in re.split(r"[,|/•·]+", formatted) if p.strip()]
            if len(parts) >= 2 and parts[-1].upper() == "IN":
                return False

    if INDIAN_CITIES.get(compact_key(city)):
        return True
    if INDIAN_STATES.get(compact_key(state)):
        return True

    parts = [p.strip() for p in re.split(r"[,|/•·;]+", blob) if p.strip()]
    for part in parts:
        key = compact_key(part)
        if key in INDIAN_CITIES or key in INDIAN_STATES:
            return True
        # multi-word city buried in office labels: "KK-Bangalore-Airtel House"
        for city_key in INDIAN_CITIES:
            if city_key in key and len(city_key) >= 5:
                return True

    return bool(re.search(r"\b(india|bharat)\b", blob, re.I))
