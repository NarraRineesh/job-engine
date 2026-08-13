"""Skill lexicon extraction from job descriptions."""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

LEXICON_PATH = Path(__file__).resolve().parents[4] / "data" / "lexicons" / "skills.txt"

_REQ_HEADERS = re.compile(
    r"(?is)(?:^|\n)\s*(?:requirements?|qualifications?|must[\s-]?have|"
    r"what you.?ll need|you have|required skills?)\s*[:\n]"
)
_PREF_HEADERS = re.compile(
    r"(?is)(?:^|\n)\s*(?:nice[\s-]?to[\s-]?have|preferred|bonus|"
    r"good to have|pluses?)\s*[:\n]"
)


@lru_cache(maxsize=1)
def load_skills() -> list[str]:
    if not LEXICON_PATH.exists():
        return []
    skills = []
    for line in LEXICON_PATH.read_text(encoding="utf-8").splitlines():
        s = line.strip().lower()
        if s and not s.startswith("#"):
            skills.append(s)
    # longer first for matching
    skills.sort(key=len, reverse=True)
    return skills


def _find_skills(text: str, skills: list[str]) -> list[str]:
    hay = text.lower()
    found: list[str] = []
    for skill in skills:
        if len(skill) <= 2:
            pat = rf"(?<![a-z0-9]){re.escape(skill)}(?![a-z0-9])"
        else:
            pat = rf"(?<![a-z]){re.escape(skill)}(?![a-z])"
        if re.search(pat, hay):
            found.append(skill)
        if len(found) >= 25:
            break
    return found


def _section(text: str, header: re.Pattern[str]) -> str:
    m = header.search(text)
    if not m:
        return ""
    start = m.end()
    # cut at next major header-ish line
    rest = text[start:]
    nxt = re.search(r"(?im)^\s*[A-Z][A-Za-z /&]{2,40}\s*$", rest[80:] if len(rest) > 80 else "")
    if nxt:
        return rest[: 80 + nxt.start()]
    return rest[:2500]


def extract_skills(description: str = "", title: str = "") -> dict[str, list[str]]:
    skills = load_skills()
    desc = str(description or "")
    req_sec = _section(desc, _REQ_HEADERS) or desc[:4000]
    pref_sec = _section(desc, _PREF_HEADERS)
    required = _find_skills(f"{title}\n{req_sec}", skills)
    preferred = [s for s in _find_skills(pref_sec, skills) if s not in required] if pref_sec else []
    # if no section hits, use whole desc for required
    if not required and desc:
        required = _find_skills(f"{title}\n{desc[:5000]}", skills)
    return {"required": required[:25], "preferred": preferred[:25]}
