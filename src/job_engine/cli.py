"""CLI: run | plan-chunks | migrate-postgres

Simple loop: fetch → enrich (python|cursor) → push MongoDB → track.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PUSH_STATE = ROOT / "out" / "push-state.json"
DEFAULT_TRACK = ROOT / "out" / "track.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="job-engine",
        description="Fetch ATS jobs → enrich → push MongoDB (with tracking).",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run", help="Fetch → enrich → push per company")
    p_run.add_argument("--ats", type=str, default="", help="Comma list; empty=all registered")
    p_run.add_argument(
        "--mode",
        choices=("multi_tenant", "singleton"),
        default="",
        help="When --ats is empty, limit to this registry mode",
    )
    p_run.add_argument("--slug", action="append", default=[], help="Limit to board slug(s)")
    p_run.add_argument(
        "--corpus",
        type=Path,
        default=None,
        help="Optional JSONL log dir (omit to skip; GHA should not write this)",
    )
    p_run.add_argument("--max-tenants", type=int, default=None)
    p_run.add_argument("--chunk-index", type=int, default=0)
    p_run.add_argument(
        "--chunk-size",
        type=int,
        default=None,
        help="Limit to this many tenants (default: all for the ATS)",
    )
    p_run.add_argument("--concurrency", type=int, default=None)
    p_run.add_argument("--write-concurrency", type=int, default=2)
    p_run.add_argument("--timeout", type=float, default=None)
    p_run.add_argument(
        "--country",
        type=str,
        default=None,
        help="Filter by location (e.g. IN or India)",
    )
    p_run.add_argument(
        "--enrich",
        choices=("python", "cursor", "both"),
        default="python",
        help="python=ATS parsers; cursor=Cursor SDK gaps; both=python then cursor gaps",
    )
    p_run.add_argument("--skip-push", action="store_true")
    p_run.add_argument("--dry-run", action="store_true")
    p_run.add_argument("--full", action="store_true", help="Ignore content-hash push state")
    p_run.add_argument("--no-skills", action="store_true")
    p_run.add_argument("--state", type=Path, default=DEFAULT_PUSH_STATE, help="Job content-hash state")
    p_run.add_argument("--track", type=Path, default=DEFAULT_TRACK, help="Per-tenant progress file")

    p_pg = sub.add_parser(
        "migrate-postgres",
        help="One-shot copy Postgres DATABASE_URL → MongoDB",
    )

    p_plan = sub.add_parser("plan-chunks", help="Print GHA matrix JSON (one job per ATS)")
    p_plan.add_argument("--ats", type=str, default="", help="Comma list; empty=all registered")
    p_plan.add_argument(
        "--mode",
        choices=("multi_tenant", "singleton"),
        default="",
        help="Limit to multi_tenant or singleton ATS",
    )
    p_plan.add_argument(
        "--max-jobs",
        type=int,
        default=256,
        help="Cap matrix length (GitHub limit is 256; 0 = unlimited)",
    )

    args = parser.parse_args(argv)

    if args.cmd == "migrate-postgres":
        from job_engine.push.migrate_postgres import migrate

        migrate()
        return 0

    if args.cmd == "plan-chunks":
        from job_engine.companies import list_registered_ats, plan_chunks
        from job_engine.fetch.scrapers import ScraperRegistry

        mode = args.mode or None
        only = [a.strip() for a in args.ats.split(",") if a.strip()] or list_registered_ats(mode=mode)
        if mode and args.ats.strip():
            allowed = set(list_registered_ats(mode=mode, include_opt_out=True))
            only = [a for a in only if a in allowed]
        only = [a for a in only if ScraperRegistry.has_scraper(a)]
        print(json.dumps(plan_chunks(only, max_jobs=args.max_jobs)))
        return 0

    if args.cmd == "run":
        from job_engine.companies import list_registered_ats
        from job_engine.pipeline.run_stream import stream_ats

        mode = args.mode or None
        only = [a.strip() for a in args.ats.split(",") if a.strip()] or None
        if only is None and mode:
            only = list_registered_ats(mode=mode)
        elif only and mode:
            allowed = set(list_registered_ats(mode=mode, include_opt_out=True))
            only = [a for a in only if a in allowed]
        summary = stream_ats(
            only,
            corpus_dir=args.corpus,
            slugs=args.slug or None,
            max_tenants=args.max_tenants,
            chunk_index=args.chunk_index,
            chunk_size=args.chunk_size,
            concurrency=args.concurrency,
            timeout=args.timeout,
            country=args.country,
            enrich_mode=args.enrich,
            skip_push=args.skip_push,
            dry_run=args.dry_run,
            full=args.full,
            push_skills=not args.no_skills,
            write_concurrency=args.write_concurrency,
            state_path=args.state,
            track_path=args.track,
        )
        print(
            f"[run] pushed={summary['pushed']:,} errors={summary['errors']} "
            f"ats={list(summary['ats'])}"
        )
        # Per-tenant scrape/push failures are expected; fail the process only if
        # nothing landed and something went wrong.
        if summary["errors"] and summary["pushed"] == 0:
            return 1
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
