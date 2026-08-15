"""SMALLINT enum maps for job / company / skill rows."""

from __future__ import annotations

import re

EMPLOYMENT_TYPE: dict[str, int] = {
    "full_time": 1,
    "part_time": 2,
    "intern": 3,
    "internship": 3,
    "contract": 4,
    "temporary": 5,
    "freelance": 6,
}

WORK_MODE: dict[str, int] = {"remote": 1, "hybrid": 2, "onsite": 3}

SENIORITY: dict[str, int] = {
    "intern": 1,
    "fresher": 2,
    "junior": 3,
    "mid": 4,
    "mid_level": 4,
    "senior": 5,
    "lead": 6,
    "staff": 7,
    "principal": 8,
    "manager": 9,
    "director": 10,
}

STATUS: dict[str, int] = {"active": 1, "closed": 2, "draft": 3, "expired": 4}

SALARY_PERIOD: dict[str, int] = {
    "hour": 1,
    "hourly": 1,
    "month": 2,
    "monthly": 2,
    "year": 3,
    "yearly": 3,
    "annual": 3,
    "week": 2,  # nearest product bucket if needed later
    "day": 1,
}

ATS: dict[str, int] = {
    "greenhouse": 1,
    "lever": 2,
    "ashby": 3,
    "workday": 4,
    "smartrecruiters": 5,
    "bamboohr": 6,
    "icims": 7,
    "jobvite": 8,
    "recruitee": 9,
    "teamtailor": 10,
    "oracle": 11,
    "successfactors": 12,
    "sap_successfactors": 12,
    "rippling": 13,
    "personio": 14,
    "breezy": 15,
    "breezyhr": 15,
    "workable": 16,
    "pinpoint": 17,
    "darwinbox": 18,
    "keka": 24,
    "phenom": 19,
    "seek": 20,
    "amazon": 21,
    "gem": 22,
    "google": 23,
    "adp": 25,
    "herp": 26,
    "hrmos": 27,
    "paycom": 28,
    "paylocity": 29,
    "softgarden": 30,
    "avature": 31,
    "beisen": 32,
    "beisen_legacy": 33,
    "builtin": 34,
    "bundesagentur": 35,
    "bytedance": 36,
    "cornerstone": 37,
    "dayforce": 38,
    "eightfold": 39,
    "eures": 40,
    "getonbrd": 41,
    "gupy": 42,
    "infojobs_es": 43,
    "jazzhr": 44,
    "jobbankca": 45,
    "jobs_cz": 46,
    "jobsch": 47,
    "join_com": 48,
    "manfred": 49,
    "mercor": 50,
    "meta": 51,
    "moka": 52,
    "pageup": 53,
    "recruiterbox": 54,
    "remoteok": 55,
    "taleo": 56,
    "tesla": 57,
    "thehub": 58,
    "tiktok": 59,
    "uber": 60,
    "ukg": 61,
    "usajobs": 62,
    "wanted": 63,
    "welcometothejungle": 64,
    "wellfound": 65,
    "weworkremotely": 66,
    "ycombinator": 67,
    "apple": 68,
    "arbetsformedlingen": 69,
}


def _norm(value: object) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def to_employment_type(value: object) -> int | None:
    if value is None or value == "" or value == "unknown":
        return None
    if isinstance(value, int):
        return value
    return EMPLOYMENT_TYPE.get(_norm(value))


def to_work_mode(value: object) -> int | None:
    if value is None or value == "" or value == "unknown":
        return None
    if isinstance(value, int):
        return value
    return WORK_MODE.get(_norm(value))


def to_seniority(value: object) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, int):
        return value
    return SENIORITY.get(_norm(value))


def normalize_title(title: object) -> str:
    s = str(title or "").lower()
    s = re.sub(r"[^a-z0-9+#]+", " ", s).strip()
    return re.sub(r"\s+", " ", s)


def to_status(value: object) -> int:
    if value is None or value == "":
        return STATUS["active"]
    if isinstance(value, int):
        return value
    return STATUS.get(_norm(value), STATUS["active"])


def to_salary_period(value: object) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, int):
        return value
    return SALARY_PERIOD.get(_norm(value))


def to_ats(value: object) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, int):
        return value
    return ATS.get(_norm(value))


def company_slug(ats: str, board_slug: str) -> str:
    a = str(ats or "").strip().lower()
    s = str(board_slug or "").strip()
    if not a or not s:
        return ""
    return f"{a}:{s}"
