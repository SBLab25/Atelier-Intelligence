"""
CJI CLI Entry Point
====================
Handles all non-dashboard operations via argparse.

CRITICAL RULE: CJI_MODE must be set in os.environ BEFORE importing graph or
config, because config.py reads CJI_MODE at import time.

Usage:
  cji --mode demo --generate-data
  cji --mode demo --run
  cji --approve --thread-id {UUID}
  cji --mode demo --run --auto-approve
  cji --resume --thread-id {UUID}
  cji --status --thread-id {UUID}
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from uuid import uuid4


# ─────────────────────────────────────────────────────────────────────────────
# Argument parsing MUST happen before any project imports
# so that --mode can be applied to os.environ before config.py is loaded.
# ─────────────────────────────────────────────────────────────────────────────
def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="cji",
        description="Customer Journey Intelligence — CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  cji --mode demo --generate-data
  cji --mode demo --run
  cji --mode demo --run --auto-approve
  cji --approve --thread-id xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
  cji --resume --thread-id xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
  cji --status --thread-id xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
  cji --mode realtime --run --window-mins 60
        """,
    )
    parser.add_argument(
        "--mode",
        choices=["demo", "realtime"],
        default=None,
        help="Override CJI_MODE env var. Must be set before --run.",
    )
    parser.add_argument(
        "--generate-data",
        action="store_true",
        help="Generate synthetic demo data to data/events.parquet (demo mode only).",
    )
    parser.add_argument(
        "--sessions",
        type=int,
        default=2000,
        help="Number of user sessions for --generate-data (default: 2000).",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for --generate-data (default: 42).",
    )
    parser.add_argument(
        "--ingest",
        action="store_true",
        help="Run Smart Ingestion before the main pipeline. Use with --file.",
    )
    parser.add_argument(
        "--file",
        nargs="+",
        default=[],
        help="Path(s) to raw data file(s) to ingest. Accepts CSV, JSON, Excel, Parquet.",
    )
    parser.add_argument(
        "--source-hint",
        type=str,
        default="",
        help="Optional hint for LLM schema detection e.g. 'GA4 export', 'Hotjar recording'.",
    )
    parser.add_argument(
        "--run",
        action="store_true",
        help="Run the full analysis pipeline (requires data).",
    )
    parser.add_argument(
        "--auto-approve",
        action="store_true",
        help="Skip human approval gate — report is generated immediately.",
    )
    parser.add_argument(
        "--approve",
        action="store_true",
        help="Resume a paused analysis thread and generate report.",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Continue an interrupted or failed run from its last checkpoint (Spec 09).",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Print a run's status, steps and errors as JSON (Spec 09).",
    )
    parser.add_argument(
        "--thread-id",
        type=str,
        default=None,
        help="Run (thread) ID for --approve, --resume or --status (printed by --run).",
    )
    parser.add_argument(
        "--window-mins",
        type=int,
        default=60,
        help="Realtime analysis window in minutes (default: 60).",
    )
    parser.add_argument(
        "--window-days",
        type=int,
        default=30,
        help="Demo analysis window in days (default: 30).",
    )
    return parser.parse_args(argv)


def _configure_console(*streams) -> None:
    """Print characters the console cannot encode as '?' instead of failing (e.g. cp1252 consoles)."""
    for stream in streams or (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(errors="replace")


class _ProgressPrinter:
    """Prints worker statuses and errors as they are added to the run state (each entry once)."""

    def __init__(self) -> None:
        self.statuses = 0
        self.errors = 0

    def __call__(self, values: dict, baseline: bool) -> None:
        statuses = values.get("worker_statuses") or []
        errors = values.get("errors") or []
        if not baseline:
            for s in statuses[self.statuses:]:
                icon = "[OK]" if s.get("status") in ("success", "skipped") else "[FAIL]"
                print(f"  {icon} {s.get('worker')}: {s.get('message')}")
            for err in errors[self.errors:]:
                msg = err
                if isinstance(err, dict):
                    msg = f"[{err.get('ts', '')}] {err.get('worker', 'unknown')}: {err.get('error', repr(err))}"
                print(f"  [WARN] {msg}")
        self.statuses, self.errors = len(statuses), len(errors)


def _report_outcome(outcome, settings, mode, journey_config, write_last_run) -> int:
    """Print the run's end state; write data/last_run.json when it completed. Exit code 0 / 1."""
    run_id = outcome.run_id
    values = outcome.values
    if outcome.already:
        if outcome.status == "completed":
            print(f"\n[DONE] Run {run_id} was already approved and completed -> {outcome.report_path}")
        else:
            print(f"\n[INFO] Run {run_id} is already approved ({outcome.status}); "
                  f"continue it with: cji --resume --thread-id {run_id}")
        return 0
    if outcome.status == "awaiting_approval":
        print(f"\n[PAUSED] Analysis paused - {len(values.get('insights') or [])} insights ready for review.")
        print("  Run to approve and generate report:")
        print(f"  cji --approve --thread-id {run_id}")
        return 0
    if outcome.status == "failed":
        failure = outcome.failure or {}
        print(f"\n[FAILED] {failure.get('worker', 'workflow')}: {failure.get('code')}: {failure.get('message')}",
              file=sys.stderr)
        print(f"  Inspect:  cji --status --thread-id {run_id}", file=sys.stderr)
        print(f"  Resume after fixing the cause:  cji --resume --thread-id {run_id}", file=sys.stderr)
        return 1
    try:
        out = write_last_run(settings.storage.last_run_file, values, mode=mode,
                             journey_name=journey_config.get("name", "onboarding"))
        print(f"  [INFO] Dashboard data saved -> {out}")
    except (OSError, TypeError, ValueError) as exc:
        print(f"[ERROR] last_run.json: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    if outcome.report_path:
        print(f"\n[DONE] Report generated -> {outcome.report_path}")
    else:
        print("\n[DONE] Analysis complete.")
    return 0


def main(argv: list[str] | None = None) -> int:
    """`cji` entry point. Returns exit code (0 = success, 1 = error, 2 = configuration error)."""
    args = _parse_args(argv)
    _configure_console()
    from cji.logs import (
        configure_logging,  # no settings import: CJI_MODE is applied below first
    )

    configure_logging()

    # ── Set CJI_MODE BEFORE importing config ─────────────────────────────────
    if args.mode:
        os.environ["CJI_MODE"] = args.mode

    # Now safe to import project modules. Configuration is validated once, here (Spec 04).
    from cji.settings import ConfigError

    try:
        from cji.config import (
            CJI_MODE,
            EVENTS_PARQUET,
            JOURNEY_CONFIG,
        )
        from cji.settings import get_settings, require

        settings = require(get_settings(), "cli")
    except ConfigError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 2

    # ── --generate-data ───────────────────────────────────────────────────────
    if args.generate_data:
        if CJI_MODE != "demo":
            print("[ERROR] --generate-data is only available in demo mode. Set CJI_MODE=demo.")
            return 1
        print(f"[INFO] Generating synthetic demo data ({args.sessions} sessions, seed={args.seed})...")
        from cji.tools.synthetic_data import generate_demo_data
        out = generate_demo_data(
            n_sessions=args.sessions,
            seed=args.seed,
            output_path=EVENTS_PARQUET,
        )
        print(f"[OK] Data generated -> {out}")
        if not args.run:
            return 0

    # ── --run / --approve / --resume / --status (Spec 09: workflow.runtime) ────────────
    if args.run or args.approve or args.resume or args.status:
        import asyncio
        import json as _json

        from cji.services.runs import cli_status
        from cji.workflow.errors import WorkflowRuntimeError
        from cji.workflow.runtime import Workflow, initial_state, write_last_run

        if (args.approve or args.resume or args.status) and not args.thread_id:
            flag = "--approve" if args.approve else ("--resume" if args.resume else "--status")
            print(f"[ERROR] {flag} requires --thread-id. Pass the thread ID printed by --run.", file=sys.stderr)
            return 1

        printer = _ProgressPrinter()
        workflow = Workflow(settings.storage.checkpoints_db, on_event=printer)

        async def _execute():
            if args.status or args.approve or args.resume:
                status = await cli_status(workflow, args.thread_id)    # RunNotFound / LegacyRun before any work
                if args.status:
                    return status
            from cji.tools.mcp_client import ping_all_servers
            print("  [INFO] Verifying MCP server connections...")
            await ping_all_servers()
            if args.approve:
                print(f"\n[INFO] Approving thread {args.thread_id} ...")
                return await workflow.approve(args.thread_id)
            if args.resume:
                print(f"\n[INFO] Resuming thread {args.thread_id} ...")
                return await workflow.resume(args.thread_id)
            state = initial_state(
                mode=CJI_MODE, journey_name=JOURNEY_CONFIG["name"], journey_steps=JOURNEY_CONFIG["steps"],
                auto_approve=args.auto_approve, window_days=args.window_days, window_mins=args.window_mins,
                collector_url=settings.services.get("collector").url,
                pending_files=[{"file_path": f, "source_hint": args.source_hint} for f in args.file]
                if args.ingest else [],
            )
            run_id = str(uuid4())
            print(f"\n{'='*60}")
            print(f"  CJI Analysis - Mode: {CJI_MODE.upper()}")
            print(f"  Thread ID: {run_id}")
            print(f"{'='*60}\n")
            return await workflow.start(state, run_id=run_id)

        try:
            outcome = asyncio.run(_execute())
        except WorkflowRuntimeError as exc:
            print(f"[ERROR] {exc}", file=sys.stderr)
            return 1
        except RuntimeError as exc:      # e.g. ping_all_servers: "Startup check failed for ..."
            print(f"[ERROR] {exc}", file=sys.stderr)
            return 1
        except (sqlite3.Error, OSError) as exc:
            print(f"[ERROR] checkpoint store: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 1

        if args.status:
            print(_json.dumps(outcome, indent=2, default=str))
            return 0
        return _report_outcome(outcome, settings, CJI_MODE, JOURNEY_CONFIG, write_last_run)

    # ── No action specified ───────────────────────────────────────────────────
    print("No action specified. Use --help to see available commands.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
