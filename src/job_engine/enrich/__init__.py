"""Enrich jobs: Python ATS parsers and optional Cursor SDK gap-fill."""

from __future__ import annotations

import json
import os
import re
from typing import Any, Literal

from job_engine.parsers import get_parser

EnrichMode = Literal["python", "cursor", "both"]


def enrich_row(
    row: dict[str, Any],
    *,
    ats: str,
    company_slug_hint: str | None = None,
    mode: EnrichMode = "python",
) -> dict[str, Any]:
    """Parse one scrape row into a nested job dict."""
    parser = get_parser(ats)
    nested = parser.parse_row(row, company_slug_hint=company_slug_hint).model_dump(mode="json")
    if mode in {"cursor", "both"} and _needs_cursor(nested):
        nested = fill_gaps_with_cursor([nested])[0]
    return nested


def enrich_jobs(
    jobs: list[dict[str, Any]],
    *,
    mode: EnrichMode = "python",
    batch_size: int = 8,
) -> list[dict[str, Any]]:
    """Apply Cursor gap-fill to already-parsed nested jobs when mode requests it."""
    if mode == "python" or not jobs:
        return jobs
    out: list[dict[str, Any]] = []
    pending: list[dict[str, Any]] = []
    for job in jobs:
        if mode == "cursor" or _needs_cursor(job):
            pending.append(job)
            if len(pending) >= batch_size:
                out.extend(fill_gaps_with_cursor(pending))
                pending = []
        else:
            out.append(job)
    if pending:
        out.extend(fill_gaps_with_cursor(pending))
    return out


def _needs_cursor(job: dict[str, Any]) -> bool:
    skills = job.get("skills") if isinstance(job.get("skills"), dict) else {}
    loc = job.get("location") if isinstance(job.get("location"), dict) else {}
    company = job.get("company") if isinstance(job.get("company"), dict) else {}
    exp = job.get("experience") if isinstance(job.get("experience"), dict) else {}
    if not (skills.get("required") or []):
        return True
    if not loc.get("countryCode") and not loc.get("country"):
        return True
    if job.get("employmentType") in (None, "", "unknown"):
        return True
    if exp.get("min") is None and exp.get("max") is None:
        return True
    if not (company.get("name") or "").strip():
        return True
    return False


def fill_gaps_with_cursor(jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Fill missing skills / location / employment / experience / company via Cursor SDK.

    Requires ``CURSOR_API_KEY``. On any failure, returns jobs unchanged.
    """
    if not jobs:
        return jobs
    api_key = os.environ.get("CURSOR_API_KEY", "").strip()
    if not api_key:
        print("[enrich] CURSOR_API_KEY missing — skipping cursor fill")
        return jobs
    try:
        from cursor_sdk import Agent, AgentOptions, LocalAgentOptions
    except ImportError:
        print("[enrich] cursor-sdk not installed — pip install 'job-engine[cursor]'")
        return jobs

    model = os.environ.get("CURSOR_MODEL", "composer-2.5")
    prompt = _build_prompt(jobs)
    try:
        result = Agent.prompt(
            prompt,
            AgentOptions(model=model, api_key=api_key, local=LocalAgentOptions(cwd=".")),
        )
        text = getattr(result, "result", None) or getattr(result, "text", None) or str(result)
        if callable(text):
            text = text()
        patches = _parse_json_array(str(text))
    except Exception as exc:  # noqa: BLE001
        print(f"[enrich] cursor failed: {type(exc).__name__}: {exc}")
        return jobs

    by_id = {str(p.get("id")): p for p in patches if isinstance(p, dict) and p.get("id")}
    out: list[dict[str, Any]] = []
    for job in jobs:
        patch = by_id.get(str(job.get("id")))
        out.append(_apply_patch(job, patch) if patch else job)
    return out


def _build_prompt(jobs: list[dict[str, Any]]) -> str:
    payload = []
    for job in jobs:
        desc = str(job.get("description") or "")[:3000]
        payload.append(
            {
                "id": job.get("id"),
                "title": job.get("title"),
                "company": (job.get("company") or {}).get("name"),
                "location": job.get("location"),
                "employmentType": job.get("employmentType"),
                "workMode": job.get("workMode"),
                "experience": job.get("experience"),
                "skills": job.get("skills"),
                "description": desc,
            }
        )
    return (
        "You enrich job postings. For each job, fill ONLY missing gaps. "
        "Do not invent salary. Use ISO countryCode when the country is clear. "
        "Return a JSON array only (no markdown) with objects:\n"
        '{"id":"...","employmentType":"full_time|part_time|contract|intern|temporary|freelance|unknown",'
        '"workMode":"remote|hybrid|onsite|unknown",'
        '"experience":{"min":0,"max":0},'
        '"location":{"countryCode":"US","country":"United States","state":"...","city":"...","formatted":"..."},'
        '"skills":{"required":["python"],"preferred":[]},'
        '"company":{"name":"..."}}\n\n'
        f"Jobs:\n{json.dumps(payload, ensure_ascii=False)}"
    )


def _parse_json_array(text: str) -> list[dict[str, Any]]:
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        text = fence.group(1).strip()
    start = text.find("[")
    end = text.rfind("]")
    if start < 0 or end < 0:
        return []
    data = json.loads(text[start : end + 1])
    return data if isinstance(data, list) else []


def _apply_patch(job: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    out = dict(job)
    if out.get("employmentType") in (None, "", "unknown") and patch.get("employmentType"):
        out["employmentType"] = patch["employmentType"]
    if out.get("workMode") in (None, "", "unknown") and patch.get("workMode"):
        out["workMode"] = patch["workMode"]

    exp = dict(out.get("experience") or {})
    pexp = patch.get("experience") if isinstance(patch.get("experience"), dict) else {}
    if exp.get("min") is None and pexp.get("min") is not None:
        exp["min"] = pexp.get("min")
    if exp.get("max") is None and pexp.get("max") is not None:
        exp["max"] = pexp.get("max")
    out["experience"] = exp

    loc = dict(out.get("location") or {})
    ploc = patch.get("location") if isinstance(patch.get("location"), dict) else {}
    for key in ("countryCode", "country", "state", "city", "formatted"):
        if not loc.get(key) and ploc.get(key):
            loc[key] = ploc[key]
    out["location"] = loc

    skills = dict(out.get("skills") or {})
    pskills = patch.get("skills") if isinstance(patch.get("skills"), dict) else {}
    if not (skills.get("required") or []) and pskills.get("required"):
        skills["required"] = [str(s).lower() for s in pskills["required"] if s]
    if not (skills.get("preferred") or []) and pskills.get("preferred"):
        skills["preferred"] = [str(s).lower() for s in pskills["preferred"] if s]
    out["skills"] = skills

    company = dict(out.get("company") or {})
    pco = patch.get("company") if isinstance(patch.get("company"), dict) else {}
    if not (company.get("name") or "").strip() and pco.get("name"):
        company["name"] = pco["name"]
    out["company"] = company
    return out
