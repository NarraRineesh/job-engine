"""Load company slug inventories (ats-companies JSON) + ATS registry."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
COMPANIES_DIR = ROOT / "data" / "companies" / "ats-companies"
REGISTRY_PATH = ROOT / "data" / "companies" / "ats_registry.json"


def _slugify_name(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    return s or "unknown"


@lru_cache(maxsize=1)
def load_registry() -> dict[str, Any]:
    if not REGISTRY_PATH.exists():
        return {"defaults": {"concurrency": 8, "timeout": 45.0}, "slug_from": {}, "ats": {}}
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def list_registered_ats() -> list[str]:
    reg = load_registry()
    return sorted((reg.get("ats") or {}).keys())


def ats_config(ats: str) -> dict[str, Any]:
    reg = load_registry()
    cfg = dict((reg.get("ats") or {}).get(ats.strip().lower()) or {})
    defaults = reg.get("defaults") or {}
    cfg.setdefault("concurrency", defaults.get("concurrency", 8))
    cfg.setdefault("timeout", defaults.get("timeout", 45.0))
    return cfg


@lru_cache(maxsize=64)
def load_ats_companies(ats: str) -> dict[str, str]:
    """Return maps: lower(name)->slug and slug->slug for one ATS."""
    by_name: dict[str, str] = {}
    for row in _iter_company_rows(ats):
        name = (row.get("name") or "").strip()
        slug = (row.get("slug") or "").strip()
        if not slug:
            url = (row.get("url") or "").strip()
            if url:
                slug = url.rstrip("/").rsplit("/", 1)[-1]
            elif name:
                slug = _slugify_name(name)
        if not slug:
            continue
        if name:
            by_name[name.lower()] = slug
        by_name[slug.lower()] = slug
    return by_name


def resolve_slug(ats: str, company_name: str, hint: str | None = None) -> str:
    """Best-effort board slug for india job id."""
    if hint and hint.strip():
        return hint.strip()
    mapping = load_ats_companies(ats)
    key = (company_name or "").strip().lower()
    if key in mapping:
        return mapping[key]
    for name, slug in mapping.items():
        if key and (key in name or name in key):
            return slug
    return _slugify_name(company_name or "unknown")


def _iter_company_rows(ats: str) -> list[dict[str, str]]:
    """Load ``{ats}.json`` tenant rows."""
    json_path = COMPANIES_DIR / f"{ats.strip().lower()}.json"
    if not json_path.exists():
        return []
    data = json.loads(json_path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        return []
    return [
        {str(k): str(v).strip() for k, v in row.items() if v not in (None, "")}
        for row in data
        if isinstance(row, dict)
    ]


def load_tenants(
    ats: str,
    *,
    only_slugs: set[str] | None = None,
    max_tenants: int | None = None,
) -> list[dict[str, str]]:
    """Load scrape targets for an ATS.

    Each item: {board_slug, scraper_slug, name, url, locale?, country?}
    """
    ats = ats.strip().lower()
    cfg = ats_config(ats)
    reg = load_registry()
    slug_from = (reg.get("slug_from") or {}).get(ats, "slug")

    if cfg.get("mode") == "singleton":
        slug = str(cfg.get("slug") or ats)
        if only_slugs and slug not in only_slugs and ats not in only_slugs:
            return []
        return [{"board_slug": slug, "scraper_slug": slug, "name": slug, "url": ""}]

    tenants: list[dict[str, str]] = []
    for row in _iter_company_rows(ats):
        name = (row.get("name") or "").strip()
        url = (row.get("url") or "").strip()
        board_slug = (row.get("slug") or "").strip()
        if not board_slug:
            if url:
                host = url.split("://", 1)[-1].split("/", 1)[0]
                board_slug = host.split(".")[0] if "." in host else url.rstrip("/").rsplit("/", 1)[-1]
            elif name:
                board_slug = _slugify_name(name)
        if not board_slug:
            continue
        if only_slugs and board_slug not in only_slugs and board_slug.lower() not in {
            s.lower() for s in only_slugs
        }:
            continue

        if slug_from == "url":
            scraper_slug = url or board_slug
            if ats == "workday" and not scraper_slug.startswith("http"):
                rebuilt = _workday_url(board_slug) or _workday_url(scraper_slug)
                if rebuilt:
                    scraper_slug = rebuilt
                    url = url or rebuilt
                    if "|" in board_slug:
                        left, _, right = board_slug.split("|", 2)
                        board_slug = f"{left}/{right}"
            elif scraper_slug and not scraper_slug.startswith("http") and ats in {
                "taleo", "oracle", "successfactors", "icims"
            }:
                if ats == "taleo" and "." in scraper_slug:
                    scraper_slug = f"https://{scraper_slug}"
        else:
            scraper_slug = board_slug or url

        if not scraper_slug:
            continue

        item = {
            "board_slug": board_slug,
            "scraper_slug": scraper_slug,
            "name": name or board_slug,
            "url": url,
        }
        if row.get("locale"):
            item["locale"] = (row.get("locale") or "").strip()
        if row.get("country"):
            item["country"] = (row.get("country") or "").strip()
        tenants.append(item)

    if ats == "workday":
        tenants = _dedupe_by_scraper_slug(tenants)
    if max_tenants is not None:
        tenants = tenants[:max_tenants]
    return tenants


def _workday_url(slug: str) -> str | None:
    """Turn ``company|wdN|site`` into a careers URL."""
    parts = slug.split("|")
    if len(parts) != 3:
        return None
    company, instance, site = (p.strip() for p in parts)
    if not (company and instance.startswith("wd") and site):
        return None
    return f"https://{company}.{instance}.myworkdayjobs.com/{site}"


def _dedupe_by_scraper_slug(tenants: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: dict[str, dict[str, str]] = {}
    order: list[str] = []
    for tenant in tenants:
        key = tenant["scraper_slug"].rstrip("/").lower()
        prev = seen.get(key)
        if prev is None:
            seen[key] = tenant
            order.append(key)
        elif tenant.get("url") and not prev.get("url"):
            seen[key] = tenant
    return [seen[k] for k in order]


def chunk_tenants(
    tenants: list[dict[str, str]],
    *,
    chunk_index: int = 0,
    chunk_size: int = 50,
) -> list[dict[str, str]]:
    """Return one zero-based chunk of tenants."""
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if chunk_index < 0:
        raise ValueError("chunk_index must be >= 0")
    start = chunk_index * chunk_size
    return tenants[start : start + chunk_size]


def plan_chunks(
    ats_list: list[str],
    *,
    chunk_size: int = 50,
) -> list[dict[str, Any]]:
    """Build GHA matrix entries: {ats, chunk, chunk_size, tenant_count}."""
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    matrix: list[dict[str, Any]] = []
    for ats in ats_list:
        tenants = load_tenants(ats)
        n = len(tenants)
        if n == 0:
            matrix.append({"ats": ats, "chunk": 0, "chunk_size": chunk_size, "tenant_count": 0})
            continue
        n_chunks = (n + chunk_size - 1) // chunk_size
        for i in range(n_chunks):
            matrix.append(
                {
                    "ats": ats,
                    "chunk": i,
                    "chunk_size": chunk_size,
                    "tenant_count": min(chunk_size, n - i * chunk_size),
                }
            )
    return matrix
