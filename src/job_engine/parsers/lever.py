"""Lever-specific parsing."""

from __future__ import annotations

import json
import re
from typing import Any

from job_engine.parsers.base import BaseAtsParser
from job_engine.parsers.shared.employment import normalize_employment_type
from job_engine.parsers.shared.work_mode import normalize_work_mode


class LeverParser(BaseAtsParser):
    ats = "lever"

    def enrich_skills(
        self, skills: dict[str, list[str]], row: dict[str, Any], description: str
    ) -> dict[str, list[str]]:
        raw = _raw(row)
        if not isinstance(raw, dict):
            return skills
        # Lever lists[] often hold requirement bullets
        lists = raw.get("lists") or []
        extra_text = []
        if isinstance(lists, list):
            for block in lists:
                if isinstance(block, dict):
                    extra_text.append(str(block.get("text") or ""))
                    extra_text.append(str(block.get("content") or ""))
        if extra_text:
            from job_engine.parsers.shared.skills import extract_skills

            more = extract_skills("\n".join(extra_text), row.get("title") or "")
            req = list(dict.fromkeys(skills["required"] + more["required"]))[:25]
            pref = [s for s in more["preferred"] if s not in req][:25]
            return {"required": req, "preferred": pref}
        return skills

    def enrich_employment_work(
        self,
        employment: str,
        work_mode: str,
        row: dict[str, Any],
        title: str,
        description: str,
    ) -> tuple[str, str]:
        raw = _raw(row)
        if isinstance(raw, dict):
            cats = raw.get("categories") or {}
            if isinstance(cats, dict):
                if employment == "unknown" and cats.get("commitment"):
                    employment = normalize_employment_type(cats["commitment"])
                if work_mode == "unknown" and cats.get("location"):
                    work_mode = normalize_work_mode(cats["location"])
                    if work_mode == "unknown" and re.search(
                        r"remote|hybrid", str(cats["location"]), re.I
                    ):
                        work_mode = (
                            "hybrid"
                            if re.search(r"hybrid", str(cats["location"]), re.I)
                            else "remote"
                        )
        return employment, work_mode


def _raw(row: dict[str, Any]) -> Any:
    raw = row.get("raw")
    if isinstance(raw, str) and raw.strip().startswith(("{", "[")):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None
    return raw
