"""Track per-tenant scrape/push progress."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def load_track(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"tenants": {}, "updatedAt": None}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"tenants": {}, "updatedAt": None}
    if not isinstance(data, dict):
        return {"tenants": {}, "updatedAt": None}
    data.setdefault("tenants", {})
    return data


def tenant_key(ats: str, board_slug: str) -> str:
    return f"{ats}:{board_slug}"


def record_tenant(
    path: Path,
    *,
    ats: str,
    board_slug: str,
    company_name: str,
    jobs_fetched: int,
    jobs_pushed: int,
    error: str | None = None,
) -> None:
    state = load_track(path)
    tenants = state.setdefault("tenants", {})
    key = tenant_key(ats, board_slug)
    tenants[key] = {
        "ats": ats,
        "boardSlug": board_slug,
        "company": company_name,
        "jobsFetched": jobs_fetched,
        "jobsPushed": jobs_pushed,
        "error": error,
        "scrapedAt": datetime.now(UTC).isoformat(),
    }
    state["updatedAt"] = datetime.now(UTC).isoformat()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
