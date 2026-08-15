"""Upsert nested jobs into MongoDB (source of truth).

Requires ``MONGODB_URI``. Reuses ``map_job`` / content-hash from ``push.map_job``.
"""

from __future__ import annotations

import json
import os
import re
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pymongo import MongoClient, UpdateOne
from pymongo.database import Database
from pymongo.errors import ConfigurationError

from job_engine.push.map_job import content_hash, map_job

CHUNK = 200
_STATE_LOCK = threading.Lock()
_INDEXED = False


def get_db() -> Database:
    uri = os.environ.get("MONGODB_URI", "").strip()
    if not uri:
        raise RuntimeError("Set MONGODB_URI")
    client = MongoClient(uri)
    try:
        db = client.get_default_database()
    except ConfigurationError:
        db = client["jobengine"]
    _ensure_indexes(db)
    return db


def _ensure_indexes(db: Database) -> None:
    global _INDEXED
    if _INDEXED:
        return
    db.jobs.create_index("status")
    db.jobs.create_index("posted_at")
    db.jobs.create_index("company.slug")
    db.jobs.create_index("skills")
    db.jobs.create_index("ats")
    db.companies.create_index("slug", unique=True)
    db.skills.create_index("normalized_name", unique=True)
    _INDEXED = True


def push_nested_jobs(
    jobs: list[dict[str, Any]],
    *,
    batch_size: int = CHUNK,
    dry_run: bool = False,
    full: bool = False,
    push_skills: bool = True,
    state_path: Path | None = None,
) -> int:
    uri = os.environ.get("MONGODB_URI", "").strip()
    if not dry_run and not uri:
        raise RuntimeError("Set MONGODB_URI")

    state: dict[str, str] = {}
    if state_path and not full:
        with _STATE_LOCK:
            loaded = _load_json(state_path, {})
            state = loaded if isinstance(loaded, dict) else {}
    next_state: dict[str, str] = dict(state) if state_path and not full else {}
    changed: list[dict[str, Any]] = []
    changed_jobs: list[dict[str, Any]] = []

    for job in jobs:
        mapped = map_job(job)
        if not mapped:
            continue
        h = content_hash(mapped)
        next_state[mapped["id"]] = h
        if full or state.get(mapped["id"]) != h:
            changed.append(mapped)
            changed_jobs.append(job)

    print(f"[push] jobs: {len(jobs):,}, changed/new: {len(changed):,}")
    if dry_run:
        print("[push] dry-run — no writes")
        return len(changed)

    db = get_db()
    now = datetime.now(UTC)
    company_ops: dict[str, UpdateOne] = {}
    job_ops: list[UpdateOne] = []
    skill_ops: dict[str, UpdateOne] = {}
    analytics_ops: list[UpdateOne] = []
    pushed_ids: list[str] = []

    raw_by_id = {j.get("id"): j for j in changed_jobs if j.get("id")}

    for m in changed:
        company = dict(m["company"])
        slug = company["slug"]
        company_ops[slug] = UpdateOne(
            {"_id": slug},
            {
                "$set": {
                    "slug": slug,
                    "name": company.get("name") or slug,
                    "logo": company.get("logo"),
                    "website": company.get("website"),
                    "industry": company.get("industry"),
                    "size": company.get("size"),
                    "type": company.get("type"),
                    "updated_at": now,
                }
            },
            upsert=True,
        )
        skills: list[str] = []
        if push_skills:
            skills = skill_names(raw_by_id.get(m["id"]) or {})
            for name in skills:
                skill_ops[name] = UpdateOne(
                    {"_id": name},
                    {
                        "$set": {
                            "name": name,
                            "normalized_name": name,
                            "last_seen": now,
                        }
                    },
                    upsert=True,
                )

        row = dict(m["job"])
        jid = str(row.pop("id"))
        row["_id"] = jid
        row["company"] = {
            "slug": slug,
            "name": company.get("name") or slug,
        }
        row["location"] = dict(m["location"])
        row["skills"] = skills
        row["content_hash"] = content_hash(m)
        row["posted_at"] = _as_dt(row.get("posted_at"))
        row["updated_at"] = _as_dt(row.get("updated_at")) or now
        row["last_scraped_at"] = _as_dt(row.get("last_scraped_at")) or now
        job_ops.append(UpdateOne({"_id": jid}, {"$set": row}, upsert=True))
        analytics_ops.append(
            UpdateOne(
                {"_id": jid},
                {
                    "$setOnInsert": {
                        "_id": jid,
                        "job_id": jid,
                        "views": 0,
                        "clicks": 0,
                        "applications": 0,
                        "saved": 0,
                    }
                },
                upsert=True,
            )
        )
        pushed_ids.append(jid)

    _bulk(db.companies, list(company_ops.values()), "companies")
    _bulk(db.jobs, job_ops, "jobs", batch_size)
    if skill_ops:
        _bulk(db.skills, list(skill_ops.values()), "skills")
    _bulk(db.job_analytics, analytics_ops, "job_analytics", batch_size)

    if state_path:
        with _STATE_LOCK:
            prev = _load_json(state_path, {})
            if not isinstance(prev, dict):
                prev = {}
            prev.update(next_state)
            state_path.parent.mkdir(parents=True, exist_ok=True)
            state_path.write_text(json.dumps(prev), encoding="utf-8")
            print(f"[push] state saved ({len(prev):,} ids) → {state_path}")
    print("[push] done")
    return len(pushed_ids)


def skill_names(job: dict[str, Any]) -> list[str]:
    block = job.get("skills") if isinstance(job.get("skills"), dict) else {}
    names: list[str] = []
    for raw in (block.get("required") or []) + (block.get("preferred") or []):
        key = re.sub(r"\s+", " ", str(raw).strip().lower())
        if key and key not in names:
            names.append(key)
    return names


def _bulk(coll, ops: list[UpdateOne], label: str, chunk: int = CHUNK) -> None:
    if not ops:
        return
    for i in range(0, len(ops), chunk):
        batch = ops[i : i + chunk]
        coll.bulk_write(batch, ordered=False)
        print(f"[push] {label}: {min(i + chunk, len(ops))}/{len(ops)}")


def _as_dt(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _load_json(path: Path, fallback: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return fallback
