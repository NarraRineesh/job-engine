"""CLI: run | plan-chunks

Simple loop: fetch → enrich (python|cursor) → push Supabase → track.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CORPUS = ROOT / "data" / "corpus"
DEFAULT_PUSH_STATE = ROOT / "out" / "push-state.json"
DEFAULT_TRACK = ROOT / "out" / "track.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="job-engine",
        description="Fetch ATS jobs → enrich → push Supabase (with tracking).",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run", help="Fetch → enrich → push per company")
    p_run.add_argument("--ats", type=str, default="", help="Comma list; empty=all registered")
    p_run.add_argument("--slug", action="append", default=[], help="Limit to board slug(s)")
    p_run.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    p_run.add_argument("--max-tenants", type=int, default=None)
    p_run.add_argument("--chunk-index", type=int, default=0)
    p_run.add_argument("--chunk-size", type=int, default=50)
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

    p_plan = sub.add_parser("plan-chunks", help="Print GHA matrix JSON for ATS tenant chunks")
    p_plan.add_argument("--ats", type=str, default="", help="Comma list; empty=all registered")
    p_plan.add_argument("--chunk-size", type=int, default=50)

    args = parser.parse_args(argv)

    if args.cmd == "plan-chunks":
        from job_engine.companies import list_registered_ats, plan_chunks

        only = [a.strip() for a in args.ats.split(",") if a.strip()] or list_registered_ats()
        print(json.dumps(plan_chunks(only, chunk_size=args.chunk_size)))
        return 0

    if args.cmd == "run":
        from job_engine.pipeline.run_stream import stream_ats

        only = [a.strip() for a in args.ats.split(",") if a.strip()] or None
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
        return 0 if summary["errors"] == 0 else 1

    return 1


if __name__ == "__main__":
    sys.exit(main())
