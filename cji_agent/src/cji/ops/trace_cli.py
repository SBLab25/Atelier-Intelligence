"""
cji-trace show TRACE_ID [--audit-dir DIR] [--json]     (Spec 15, OD-161)

Prints one trace as a tree from the audit files of every process: HTTP request spans, security records, workflow
steps, tool calls and LLM calls. A run started by a request is its own trace (derived from the run id); records of
the request that name a `run_id` pull that run's trace in, so one command follows a request through the API, the
workflow and the MCP servers.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def load(directory: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    unreadable = 0
    for path in sorted(directory.glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                record = json.loads(line)
            except ValueError:
                unreadable += 1  # a torn line from a process killed mid-write; reported below
                record = None
            if isinstance(record, dict):
                records.append(record)
    if unreadable:
        print(f"cji-trace: {unreadable} unreadable audit lines skipped", file=sys.stderr)
    return records


def collect(records: list[dict[str, Any]], trace_id: str) -> list[dict[str, Any]]:
    from cji.observability.trace import trace_id_for_run

    wanted = {trace_id}
    while True:
        runs = {r.get("run_id") for r in records if r.get("trace_id") in wanted and r.get("run_id")}
        more = {t for t in (trace_id_for_run(str(run)) for run in runs) if t} - wanted
        if not more:
            break
        wanted |= more
    found = [r for r in records if r.get("trace_id") in wanted]
    return sorted(found, key=lambda r: str(r.get("ts", "")))


def label(r: dict[str, Any]) -> str:
    kind = r.get("kind")
    if kind == "span":
        return f"{r.get('name')} -> {r.get('http_status')}"
    if kind == "tool":
        return f"tool {r.get('tool')} on {r.get('service')}"
    if kind == "tool_session":
        return f"connect {r.get('service')}"
    if kind == "llm":
        return f"llm {r.get('provider')}/{r.get('model')} ({r.get('purpose')})"
    if kind == "step":
        return f"step {r.get('worker')} attempt {r.get('attempt')}"
    if kind == "run":
        return f"run {r.get('from_status')} -> {r.get('to_status')}"
    if kind == "security":
        return f"security {r.get('action')} by {r.get('actor')}"
    return str(kind)


def render(found: list[dict[str, Any]]) -> list[str]:
    by_span: dict[str, list[dict[str, Any]]] = {}
    children: dict[str, list[dict[str, Any]]] = {}
    roots: list[dict[str, Any]] = []
    for r in found:
        if r.get("span_id"):
            by_span.setdefault(str(r["span_id"]), []).append(r)
    for r in found:
        parent = r.get("parent_id")
        own = r.get("span_id")
        if parent and str(parent) in by_span and parent != own:
            children.setdefault(str(parent), []).append(r)
        elif own and by_span[str(own)][0] is not r:
            children.setdefault(str(own), []).append(r)  # step records share their step's span
        else:
            roots.append(r)
    lines: list[str] = []

    def walk(r: dict[str, Any], depth: int) -> None:
        latency = f" {r['latency_ms']} ms" if r.get("latency_ms") is not None else ""
        outcome = f" [{r.get('outcome')}]" if r.get("outcome") else ""
        lines.append(
            f"{'  ' * depth}{str(r.get('ts', ''))[11:23]}  {label(r)}{latency}{outcome}  ({r.get('service', '-')})"
        )
        own = r.get("span_id")
        if own and by_span[str(own)][0] is r:
            for child in children.get(str(own), []):
                walk(child, depth + 1)

    for root in roots:
        walk(root, 0)
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="cji-trace", description="Show one trace from the CJI audit files.")
    commands = parser.add_subparsers(dest="command", required=True)
    show = commands.add_parser("show", help="print the span tree of a trace (or a run id)")
    show.add_argument("trace_id", help="32 hex digits from a traceparent header or a log line, or a run id")
    show.add_argument("--audit-dir", type=Path, default=None, help="default: CJI_AUDIT_DIR / <data>/audit")
    show.add_argument("--json", action="store_true", help="print the records instead of the tree")
    args = parser.parse_args(argv)
    from cji.observability.trace import trace_id_for_run

    directory = args.audit_dir
    if directory is None:
        from cji.settings import get_settings

        configured = get_settings().storage.audit_dir
        if configured is None:
            print("cji-trace: the audit directory is off (CJI_AUDIT_DIR); pass --audit-dir", file=sys.stderr)
            return 2
        directory = Path(configured)
    trace_id = trace_id_for_run(args.trace_id) or args.trace_id.strip().lower()
    found = collect(load(directory), trace_id)
    if not found:
        print(f"cji-trace: no records for {trace_id} in {directory}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(found, indent=2))
    else:
        services = sorted({str(r.get("service")) for r in found})
        print(f"trace {trace_id}: {len(found)} records from {len(services)} processes ({', '.join(services)})")
        print("\n".join(render(found)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
