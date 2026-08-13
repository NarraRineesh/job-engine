"""Keka multi-tenant public careers scraper.

Public career boards expose::

    GET https://{tenant}.keka.com/careers/api/jobs/{portal}/active

When the board ``portalName`` meta is empty, ``portal`` is ``default``.
Listings include descriptions, locations, salary, and skills — no detail
fan-out required. Uses the authenticated Hire API is intentionally avoided.
"""

from __future__ import annotations

import html
import re
from datetime import UTC, datetime
from typing import Any, ClassVar
from urllib.parse import urlparse

from pydantic import HttpUrl

from job_engine.fetch.exceptions import ScraperError
from job_engine.fetch.models import ATSType, EmploymentType, Job
from job_engine.fetch.scrapers.base import BaseScraper, ScraperRegistry

_TENANT_RE = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", re.IGNORECASE)
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")

# Keka Hire jobType enum: 1=PartTime, 2=FullTime (docs); observed 2 for FTE.
_JOB_TYPE_MAP: dict[int, EmploymentType] = {
    1: "PART_TIME",
    2: "FULL_TIME",
}

# Observed salaryPeriod: 4 = annual INR ranges on public boards.
_SALARY_PERIOD_MAP: dict[int, str] = {
    1: "HOUR",
    2: "DAY",
    3: "MONTH",
    4: "YEAR",
    5: "YEAR",
}


@ScraperRegistry.register(ATSType.KEKA)
class KekaScraper(BaseScraper):
    """Scrape one Keka tenant from a bare slug or careers URL."""

    ats = ATSType.KEKA
    fetch_engine = "httpx"
    fetch_escalate = True
    default_headers: ClassVar[dict[str, str]] = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-IN,en;q=0.9",
    }

    async def afetch(self) -> list[Job]:
        tenant = self._resolve_tenant()
        base_url = f"https://{tenant}.keka.com"
        portal = await self._resolve_portal(base_url)
        api_url = f"{base_url}/careers/api/jobs/{portal}/active"
        headers = {
            **self.default_headers,
            "Referer": f"{base_url}/careers",
            "Origin": base_url,
        }

        async with self.make_fetcher(headers=headers) as fetch:
            payload = await fetch.get_json(api_url)

        if not isinstance(payload, list):
            raise ScraperError(f"Keka returned a non-list payload for {tenant!r}: {type(payload)}")

        company_name = await self._company_name(base_url, portal) or tenant
        jobs: list[Job] = []
        seen: set[str] = set()
        for item in payload:
            if not isinstance(item, dict):
                continue
            job = self._parse_listing(item, tenant=tenant, company=company_name, base_url=base_url)
            if job is None or not job.ats_id or job.ats_id in seen:
                continue
            seen.add(job.ats_id)
            jobs.append(job)
        return jobs

    async def _resolve_portal(self, base_url: str) -> str:
        """Read careers HTML meta portalName; empty → default."""
        try:
            async with self.make_fetcher(headers=self.default_headers) as fetch:
                html_text = await fetch.get_text(f"{base_url}/careers")
        except Exception:  # noqa: BLE001
            return "default"
        match = re.search(
            r'<meta\s+name=["\']portalName["\']\s*(?:content=["\']([^"\']*)["\'])?',
            html_text,
            re.I,
        )
        if not match:
            match = re.search(
                r'<meta\s+name=["\']portalName["\'][^>]*>',
                html_text,
                re.I,
            )
            if match and "content=" not in match.group(0):
                return "default"
            return "default"
        portal = (match.group(1) or "").strip()
        return portal or "default"

    async def _company_name(self, base_url: str, portal: str) -> str | None:
        url = f"{base_url}/careers/api/organization/{portal}/careerportalinfo"
        try:
            async with self.make_fetcher(headers=self.default_headers) as fetch:
                info = await fetch.get_json(url)
        except Exception:  # noqa: BLE001
            return None
        if isinstance(info, dict):
            name = info.get("name") or info.get("shortName")
            if isinstance(name, str) and name.strip():
                return name.strip()
        return None

    def _resolve_tenant(self) -> str:
        raw = self.company_slug.strip()
        if not raw:
            raise ScraperError("Keka scraper requires a non-empty company_slug")
        if "://" in raw:
            host = (urlparse(raw).hostname or "").lower()
            match = re.fullmatch(rf"({_TENANT_RE.pattern})\.keka\.com", host)
            if not match:
                raise ScraperError(f"Keka slug must be a *.keka.com URL, got {raw!r}")
            return match.group(1).lower()
        tenant = raw.lower().removesuffix(".keka.com")
        if not _TENANT_RE.fullmatch(tenant):
            raise ScraperError(
                f"Keka slug {raw!r} looks malformed; expected a DNS-safe subdomain"
            )
        return tenant

    def _parse_listing(
        self,
        item: dict[str, Any],
        *,
        tenant: str,
        company: str,
        base_url: str,
    ) -> Job | None:
        ats_id = str(item.get("id") or "").strip()
        title = str(item.get("title") or "").strip()
        if not ats_id or not title:
            return None

        location, country_iso = _format_locations(item.get("jobLocations"))
        sal_currency, sal_period, sal_min, sal_max, sal_summary = _parse_salary(
            item.get("salaryRange"), item.get("salaryRangeFormat")
        )
        employment = _JOB_TYPE_MAP.get(int(item["jobType"])) if _is_int(item.get("jobType")) else None
        experience = _parse_experience_years(item.get("experience"))
        description = _html_to_text(item.get("description")) or _html_to_text(item.get("excerpt"))
        apply_url = f"{base_url}/careers/job/{ats_id}"
        skills = item.get("skillNames") if isinstance(item.get("skillNames"), list) else []

        raw: dict[str, Any] = {
            "tenant": tenant,
            "departmentName": item.get("departmentName"),
            "departmentIdentifier": item.get("departmentIdentifier"),
            "jobType": item.get("jobType"),
            "experience": item.get("experience"),
            "salaryRange": item.get("salaryRange"),
            "salaryRangeFormat": item.get("salaryRangeFormat"),
            "skillNames": skills,
            "jobLocations": item.get("jobLocations"),
            "publishedSinceDays": item.get("publishedSinceDays"),
        }

        return Job(
            url=HttpUrl(apply_url),
            title=title,
            company=company,
            ats_type=ATSType.KEKA,
            ats_id=ats_id,
            location=location,
            country_iso=country_iso,
            is_remote=_infer_remote(location, title, description or ""),
            department=str(item.get("departmentName") or "").strip() or None,
            employment_type=employment,
            experience=experience,
            salary_currency=sal_currency,
            salary_period=sal_period,  # type: ignore[arg-type]
            salary_min=sal_min,
            salary_max=sal_max,
            salary_summary=sal_summary,
            description=description,
            apply_url=HttpUrl(apply_url),
            posted_at=_parse_iso(item.get("publishedOn")),
            fetched_at=datetime.now(UTC),
            language="en",
            raw=raw,
        )


def _format_locations(value: Any) -> tuple[str | None, str | None]:
    if not isinstance(value, list) or not value:
        return None, None
    parts: list[str] = []
    country_iso: str | None = None
    for loc in value:
        if not isinstance(loc, dict):
            continue
        city = str(loc.get("city") or "").strip()
        state = str(loc.get("state") or loc.get("name") or "").strip()
        country = str(loc.get("countryName") or "").strip()
        code = str(loc.get("countryCode") or "").strip().upper() or None
        if code and country_iso is None:
            country_iso = code
        chunk = ", ".join(p for p in (city, state, country) if p)
        if chunk and chunk not in parts:
            parts.append(chunk)
    if not parts:
        return None, country_iso
    return "; ".join(parts), country_iso


def _parse_salary(
    value: Any, summary: Any
) -> tuple[str | None, str | None, float | None, float | None, str | None]:
    currency: str | None = None
    period: str | None = None
    mn: float | None = None
    mx: float | None = None
    if isinstance(value, dict):
        currency = str(value.get("currency") or "").strip().upper() or None
        period_raw = value.get("salaryPeriod")
        period = _SALARY_PERIOD_MAP.get(int(period_raw)) if _is_int(period_raw) else None
        try:
            if value.get("minimum") is not None:
                mn = float(value["minimum"])
            if value.get("maximum") is not None:
                mx = float(value["maximum"])
        except (TypeError, ValueError):
            mn, mx = None, None
    summary_text = str(summary).strip() if isinstance(summary, str) and summary.strip() else None
    return currency, period, mn, mx, summary_text


def _parse_experience_years(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip()
    if not text:
        return None
    match = re.search(r"(\d+)\s*[-–to]+\s*(\d+)", text, re.I)
    if match:
        return int(match.group(1))
    match = re.search(r"(\d+)", text)
    return int(match.group(1)) if match else None


def _infer_remote(location: str | None, title: str, description: str) -> bool | None:
    blob = f"{location or ''} {title} {description}".lower()
    if re.search(r"\b(remote|work from home|wfh)\b", blob):
        return True
    return None


def _html_to_text(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    unescaped = html.unescape(value)
    text = _HTML_TAG_RE.sub(" ", unescaped)
    text = _WHITESPACE_RE.sub(" ", text).strip()
    return text[:25_000] if text else None


def _parse_iso(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed


def _is_int(value: Any) -> bool:
    try:
        int(value)
        return True
    except (TypeError, ValueError):
        return False
