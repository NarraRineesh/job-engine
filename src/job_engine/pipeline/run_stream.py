"""Per-company stream: fetch → enrich → push → track."""

from __future__ import annotations

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from job_engine.companies import (
    ats_config,
    chunk_tenants,
    list_registered_ats,
    load_tenants,
)
from job_engine.enrich import EnrichMode, enrich_jobs, enrich_row
from job_engine.parsers.shared.location import matches_country
from job_engine.track import record_tenant


def stream_ats(
    ats_list: list[str] | None,
    *,
    corpus_dir: Path | None = None,
    slugs: list[str] | None = None,
    max_tenants: int | None = None,
    chunk_index: int = 0,
    chunk_size: int | None = None,
    concurrency: int | None = None,
    timeout: float | None = None,
    country: str | None = None,
    enrich_mode: EnrichMode = "python",
    skip_push: bool = False,
    dry_run: bool = False,
    full: bool = False,
    push_skills: bool = True,
    write_concurrency: int = 2,
    state_path: Path | None = None,
    track_path: Path | None = None,
) -> dict[str, Any]:
    """Stream one or more ATS: per tenant fetch → enrich → push → track."""
    targets = [a.strip().lower() for a in (ats_list or list_registered_ats()) if a.strip()]
    summary: dict[str, Any] = {"ats": {}, "pushed": 0, "errors": 0}
    for ats in targets:
        result = asyncio.run(
            _stream_one(
                ats,
                corpus_dir=corpus_dir,
                only_slugs=set(slugs) if slugs else None,
                max_tenants=max_tenants,
                chunk_index=chunk_index,
                chunk_size=chunk_size,
                concurrency=concurrency,
                timeout=timeout,
                country=country,
                enrich_mode=enrich_mode,
                skip_push=skip_push,
                dry_run=dry_run,
                full=full,
                push_skills=push_skills,
                write_concurrency=write_concurrency,
                state_path=state_path,
                track_path=track_path,
            )
        )
        summary["ats"][ats] = result
        summary["pushed"] += int(result.get("pushed") or 0)
        summary["errors"] += int(result.get("errors") or 0)
    return summary


async def _stream_one(
    ats: str,
    *,
    corpus_dir: Path | None,
    only_slugs: set[str] | None,
    max_tenants: int | None,
    chunk_index: int,
    chunk_size: int | None,
    concurrency: int | None,
    timeout: float | None,
    country: str | None,
    enrich_mode: EnrichMode,
    skip_push: bool,
    dry_run: bool,
    full: bool,
    push_skills: bool,
    write_concurrency: int,
    state_path: Path | None,
    track_path: Path | None,
) -> dict[str, Any]:
    from job_engine.fetch.scrapers import get_scraper
    from job_engine.fetch.scrapers.base import ScraperRegistry

    if not ScraperRegistry.has_scraper(ats):
        print(f"[stream] skip {ats}: no scraper registered")
        return {"tenants": 0, "jobs": 0, "pushed": 0, "errors": 0}

    cfg = ats_config(ats)
    conc = int(concurrency if concurrency is not None else cfg.get("concurrency") or 8)
    to = float(timeout if timeout is not None else cfg.get("timeout") or 45.0)
    tenants = load_tenants(ats, only_slugs=only_slugs, max_tenants=max_tenants)
    if chunk_size is not None:
        size = int(chunk_size)
        tenants = chunk_tenants(tenants, chunk_index=chunk_index, chunk_size=size)
    else:
        size = len(tenants)
    if not tenants:
        print(f"[stream] {ats}: no tenants in chunk {chunk_index}")
        return {"tenants": 0, "jobs": 0, "pushed": 0, "errors": 0}

    sem = asyncio.Semaphore(conc)
    write_sem = asyncio.Semaphore(max(1, write_concurrency))
    push_pool = ThreadPoolExecutor(max_workers=max(1, write_concurrency))
    errors = 0
    jobs_total = 0
    pushed_total = 0
    lock = asyncio.Lock()

    if corpus_dir is not None:
        corpus_dir.mkdir(parents=True, exist_ok=True)
    corpus_path = (corpus_dir / f"{ats}.jsonl") if corpus_dir else None
    push_state = state_path or Path("out/push-state.json")
    track_file = track_path or Path("out/track.json")

    print(
        f"[stream] {ats}: {len(tenants)} tenants "
        f"chunk={chunk_index}/{size} concurrency={conc} "
        f"enrich={enrich_mode} country={country or '-'}"
    )

    async def one(tenant: dict[str, str]) -> None:
        nonlocal errors, jobs_total, pushed_total
        kwargs: dict[str, Any] = {"timeout": to}
        if ats == "phenom":
            if tenant.get("locale"):
                kwargs["locale"] = tenant["locale"]
            if tenant.get("country"):
                kwargs["country"] = tenant["country"]

        nested_jobs: list[dict[str, Any]] = []
        err: str | None = None
        async with sem:
            try:
                scraper = get_scraper(ats, tenant["scraper_slug"], **kwargs)
                raw_jobs = await scraper.afetch()
            except Exception as exc:  # noqa: BLE001
                err = f"{type(exc).__name__}: {exc}"
                async with lock:
                    errors += 1
                    print(f"  [{ats}] {tenant['board_slug']}: {err}")
                    record_tenant(
                        track_file,
                        ats=ats,
                        board_slug=tenant["board_slug"],
                        company_name=tenant.get("name") or tenant["board_slug"],
                        jobs_fetched=0,
                        jobs_pushed=0,
                        error=err,
                    )
                return

        for job in raw_jobs:
            row = _job_to_row(job)
            if not row.get("company"):
                row["company"] = tenant.get("name") or tenant["board_slug"]
            try:
                # Python parser always; cursor deferred to batch below when mode needs it
                nested = enrich_row(
                    row,
                    ats=ats,
                    company_slug_hint=tenant["board_slug"],
                    mode="python",
                )
            except Exception as exc:  # noqa: BLE001
                print(f"  [{ats}] parse {tenant['board_slug']}: {exc}")
                continue
            if country and not matches_country(nested.get("location") or {}, country):
                continue
            nested_jobs.append(nested)

        if enrich_mode in {"cursor", "both"} and nested_jobs:
            nested_jobs = await asyncio.get_running_loop().run_in_executor(
                None,
                lambda: enrich_jobs(nested_jobs, mode=enrich_mode, batch_size=8),
            )

        async with lock:
            jobs_total += len(nested_jobs)

        if corpus_path is not None and nested_jobs:
            async with lock:
                _append_corpus(corpus_path, nested_jobs)

        pushed = 0
        if skip_push:
            print(
                f"  [{ats}] {tenant['board_slug']}: {len(nested_jobs)} jobs (skip-push)"
            )
        elif not nested_jobs:
            print(f"  [{ats}] {tenant['board_slug']}: 0 jobs after filter")
        else:
            async with write_sem:
                try:
                    pushed = await asyncio.get_running_loop().run_in_executor(
                        push_pool,
                        lambda jobs=nested_jobs: _push_sync(
                            jobs,
                            dry_run=dry_run,
                            full=full,
                            push_skills=push_skills,
                            state_path=push_state,
                        ),
                    )
                except Exception as exc:  # noqa: BLE001
                    err = f"{type(exc).__name__}: {exc}"
                    async with lock:
                        errors += 1
                    print(f"  [{ats}] push {tenant['board_slug']}: {err}")
                else:
                    async with lock:
                        pushed_total += int(pushed or 0)
                    print(
                        f"  [{ats}] {tenant['board_slug']}: {len(nested_jobs)} jobs, "
                        f"pushed/changed={pushed}"
                    )

        async with lock:
            record_tenant(
                track_file,
                ats=ats,
                board_slug=tenant["board_slug"],
                company_name=tenant.get("name") or tenant["board_slug"],
                jobs_fetched=len(nested_jobs),
                jobs_pushed=int(pushed or 0),
                error=err,
            )

    try:
        await asyncio.gather(*(one(t) for t in tenants))
    finally:
        push_pool.shutdown(wait=True)

    print(
        f"[stream] {ats}: tenants={len(tenants)} jobs={jobs_total:,} "
        f"pushed={pushed_total:,} errors={errors}"
    )
    return {
        "tenants": len(tenants),
        "jobs": jobs_total,
        "pushed": pushed_total,
        "errors": errors,
    }


def _push_sync(
    jobs: list[dict[str, Any]],
    *,
    dry_run: bool,
    full: bool,
    push_skills: bool,
    state_path: Path,
) -> int:
    from job_engine.push.mongo import push_nested_jobs

    return push_nested_jobs(
        jobs,
        dry_run=dry_run,
        full=full,
        push_skills=push_skills,
        state_path=state_path,
    )


def _job_to_row(job: object) -> dict[str, Any]:
    d = job.model_dump(mode="json") if hasattr(job, "model_dump") else dict(job)  # type: ignore[arg-type]
    ats = d.get("ats_type")
    if ats is not None:
        d["ats_type"] = str(getattr(ats, "value", ats)).lower()
    return d


def _append_corpus(path: Path, new_jobs: list[dict[str, Any]]) -> None:
    existing: dict[str, dict[str, Any]] = {}
    if path.exists():
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    j = json.loads(line)
                    existing[j["id"]] = j
    for j in new_jobs:
        slim = {k: v for k, v in j.items() if k not in {"description", "summary"}}
        existing[j["id"]] = slim
    with path.open("w", encoding="utf-8") as fh:
        for j in existing.values():
            fh.write(json.dumps(j, ensure_ascii=False) + "\n")
