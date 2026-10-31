"""
Release check (Spec 15, OD-174): `python ci/release_check.py [--evidence DIR] [--checklist FILE] [--json FILE]`.

Maps every production control to a check over recorded evidence and writes one row per control: control, check,
result (pass / fail / blocked / n/a), evidence, owner and blocker. A control without evidence fails: nothing is
reported as passed unless its check ran and recorded a result. Owner items stay `blocked` until the owner records
evidence in ci/owner-evidence.json.

Evidence layout (written by the Spec 15 gate, evidence/scripts/gate_spec15.ps1):
  DIR/ci/summary.md, DIR/ci/junit/*.xml, DIR/ci/deps.json, DIR/ci/secret-scan.json   (ci/run_ci.py --network)
  DIR/recovery.jsonl                                                               (recovery suite)
  DIR/logs-check.json, metrics-check.json, trace-check.json, audit-check.json,
  DIR/ops-status.json, rollback-drill.json, canary.json                            (live phase and drills)
Each *-check.json holds {"ok": true|false, "detail": "..."}.

Prints the table and a final line READY or NOT READY (n blocked, m failed); exit 0 only for READY.
"""

from __future__ import annotations

import argparse
import json
import re
import xml.etree.ElementTree as ET  # nosec B405 - parses JUnit files this repository's own test runs wrote
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EVIDENCE = ROOT / ".kiro" / "specs" / "15-production-hardening" / "evidence" / "release"
OWNER = "Project owner"
NEXT = "next Spec"
RECOVERY_CASES = 7


@dataclass
class Row:
    control: str
    check: str
    result: str  # pass | fail | blocked | n/a
    evidence: str
    owner: str
    blocker: str
    detail: str


def _json(path: Path) -> object | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def flag_file(ev: Path, name: str, control: str, check: str) -> Row:
    path = ev / name
    data = _json(path)
    if not isinstance(data, dict) or "ok" not in data:
        return Row(control, check, "fail", _rel(path), NEXT, "evidence missing or unreadable", "no recorded result")
    ok = data.get("ok") is True
    detail = str(data.get("detail", ""))
    return Row(control, check, "pass" if ok else "fail", _rel(path), "" if ok else NEXT, "" if ok else detail, detail)


def junit_cases(ev: Path) -> list[tuple[str, str]]:
    """(classname::name, outcome) for every test case in DIR/ci/junit/*.xml."""
    cases: list[tuple[str, str]] = []
    for xml in sorted((ev / "ci" / "junit").glob("*.xml")):
        try:
            tree = ET.parse(xml)  # nosec B314 - local files written by our own test runs
        except (OSError, ET.ParseError):
            continue
        for case in tree.iter("testcase"):
            outcome = "passed"
            for child in case:
                if child.tag in ("failure", "error"):
                    outcome = "failed"
                elif child.tag == "skipped" and outcome == "passed":
                    outcome = "skipped"
            cases.append((f"{case.get('classname', '')}::{case.get('name', '')}", outcome))
    return cases


def tests_row(ev: Path, control: str, pattern: str, minimum: int) -> Row:
    cases = [(n, o) for n, o in junit_cases(ev) if re.search(pattern, n, re.IGNORECASE)]
    failed = [n for n, o in cases if o == "failed"]
    passed = [n for n, o in cases if o == "passed"]
    check = f"tests matching /{pattern}/ in JUnit"
    evidence = _rel(ev / "ci" / "junit")
    if failed:
        return Row(
            control, check, "fail", evidence, NEXT, f"{len(failed)} failed: {failed[:3]}", f"{len(passed)} passed"
        )
    if len(passed) < minimum:
        return Row(control, check, "fail", evidence, NEXT, f"only {len(passed)} passing tests (need {minimum})", "")
    return Row(control, check, "pass", evidence, "", "", f"{len(passed)} passed")


def ci_row(ev: Path) -> Row:
    path = ev / "ci" / "summary.md"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return Row(
            "CI (format, lint, types, unit, integration, browser, scans)",
            "ci/run_ci.py --network",
            "fail",
            _rel(path),
            NEXT,
            "no CI summary",
            "",
        )
    result = re.search(r"Result: (PASS|FAIL) \((.*?)\)", text)
    stages = re.search(r"stages: ([^.]*)\.", text)
    needed = {"format", "lint", "types", "unit", "integration", "browser", "scans"}
    missing = needed - set((stages.group(1) if stages else "").replace(" ", "").split(","))
    failed_steps = [ln for ln in text.splitlines() if "| FAIL |" in ln]
    ok = bool(result and result.group(1) == "PASS" and not missing)
    detail = (result.group(2) if result else "no result line") + (
        f"; stages not run: {sorted(missing)}" if missing else ""
    )
    blocker = "" if ok else "; ".join(ln.split("|")[2].strip() for ln in failed_steps) or detail
    return Row(
        "CI (format, lint, types, unit, integration, browser, scans)",
        "ci/run_ci.py --network",
        "pass" if ok else "fail",
        _rel(path),
        "" if ok else NEXT,
        blocker,
        detail,
    )


def deps_row(ev: Path) -> Row:
    path = ev / "ci" / "deps.json"
    data = _json(path)
    control, check = "Dependency scan", "ci/scans.py deps (pip-audit, npm audit) vs ci/exceptions.json"
    if not isinstance(data, dict):
        return Row(control, check, "fail", _rel(path), NEXT, "no dependency scan result", "")
    rows = data.get("advisories", [])
    errors = data.get("errors", [])
    open_rows = [r for r in rows if not str(r.get("status", "")).startswith("accepted")]
    packages = sorted({f"{r['package']} {r['version']}" for r in open_rows})
    detail = f"{len(rows)} advisories, {len(open_rows)} not accepted, {len(errors)} scanner errors"
    if errors:
        return Row(control, check, "fail", _rel(path), NEXT, "; ".join(errors)[:300], detail)
    if open_rows:
        return Row(
            control,
            check,
            "blocked",
            _rel(path),
            OWNER,
            f"upgrade or accept with expiry (ci/exceptions.json): {', '.join(packages)}",
            detail,
        )
    return Row(control, check, "pass", _rel(path), "", "", detail)


def secret_row(ev: Path) -> Row:
    path = ev / "ci" / "secret-scan.json"
    data = _json(path)
    control, check = "Secret scan", "cji_agent/scripts/secret_scan.py (tree and history)"
    if not isinstance(data, dict):
        return Row(control, check, "fail", _rel(path), NEXT, "no secret scan result", "")
    open_items = data.get("open", [])
    detail = f"{len(open_items)} open, {len(data.get('allowed', []))} allow-listed"
    if open_items:
        where = [f"{f.get('rule')} {f.get('path')}:{f.get('line')}" for f in open_items[:3]]
        return Row(control, check, "fail", _rel(path), NEXT, f"unlisted findings: {where}", detail)
    return Row(control, check, "pass", _rel(path), "", "", detail)


def recovery_row(ev: Path) -> Row:
    path = ev / "recovery.jsonl"
    control, check = "Failure injection and recovery", f"recovery suite ({RECOVERY_CASES} cases, real processes)"
    try:
        cases = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except (OSError, ValueError):
        return Row(control, check, "fail", _rel(path), NEXT, "no recovery results", "")
    passed = [c for c in cases if c.get("ok") is True]
    failed = [c.get("case") for c in cases if c.get("ok") is not True]
    detail = f"{len(passed)}/{RECOVERY_CASES} passed"
    if failed or len(passed) < RECOVERY_CASES:
        return Row(control, check, "fail", _rel(path), NEXT, f"failed or missing: {failed}", detail)
    return Row(control, check, "pass", _rel(path), "", "", detail)


def drill_rows(ev: Path) -> list[Row]:
    path = ev / "rollback-drill.json"
    data = _json(path)
    out = []
    for control, key, check in (
        ("Backup and restore", "restore_equal", "cji-backup create/verify/restore into a fresh database and home"),
        (
            "Migration rollback",
            "schema_rollback_ok",
            "cji-db migrate up/down/up; 0.11.0 runs on the rolled-back schema",
        ),
        ("Release rollback", "release_rollback_ok", "reinstall 0.11.0 wheel, run, compare results with 0.15.0"),
        ("Frontend compatibility", "old_frontend_ok", "pre-Spec 15 frontend smoke test against the 0.15.0 API"),
        ("Configuration rollback", "write_switch_ok", "CJI_API_WRITE_OPERATIONS=false stops start/resume/ingestion"),
    ):
        if not isinstance(data, dict) or key not in data:
            out.append(Row(control, check, "fail", _rel(path), NEXT, "drill result missing", ""))
            continue
        ok = data[key] is True
        detail = str(data.get(f"{key}_detail", ""))
        out.append(
            Row(
                control,
                check,
                "pass" if ok else "fail",
                _rel(path),
                "" if ok else NEXT,
                "" if ok else (detail or "drill step failed"),
                detail,
            )
        )
    return out


def owner_rows() -> list[Row]:
    path = ROOT / "ci" / "owner-evidence.json"
    data = _json(path)
    recorded = data.get("items", {}) if isinstance(data, dict) else {}
    items = [
        (
            "supabase_backups",
            "Supabase provider-side backups and restore",
            "checked in the Supabase dashboard",
            "cannot be tested from here; record the backup schedule and a restore test",
        ),
        (
            "supabase_migrations",
            "Migrations applied to the real Supabase database",
            "cji-db migrate status --require-current",
            "run `cji-backup create`, then `cji-db migrate up` (docs/deployment.md)",
        ),
        (
            "release_host",
            "TLS proxy and process supervision on the release host",
            "docs/deployment.md on the host",
            "host not provisioned; the guide has examples only",
        ),
        (
            "tracker_key_history",
            "Tracker key in git history (fingerprint 8aa90e8de3b9c744)",
            "revoke with POST /admin/api-keys/revoke or confirm it is inactive",
            "the 'Live Web Demo Key' of journey my_vercel_site is in old commits and may still be active",
        ),
        (
            "example_key_docs",
            "Example key in docs/6-API-Contracts.md (fingerprint 54d5b3115cb8abb1)",
            "confirm it was never issued",
            "unknown whether the value was ever a real key",
        ),
    ]
    rows = []
    for key, control, check, blocker in items:
        entry = recorded.get(key)
        if isinstance(entry, dict) and entry.get("status") == "pass" and entry.get("evidence"):
            rows.append(Row(control, check, "pass", _rel(path), OWNER, "", f"recorded: {entry['evidence']}"))
        else:
            rows.append(Row(control, check, "blocked", _rel(path), OWNER, blocker, "no owner evidence recorded"))
    rows += [
        Row(
            "Container scanning",
            "-",
            "n/a",
            "docs/deployment.md",
            OWNER,
            "no container image is built (OD-158); scan it if one is introduced",
            "",
        ),
        Row(
            "Hosted CI",
            "-",
            "n/a",
            "ci/run_ci.py",
            OWNER,
            "the project is not pushed; ci/run_ci.py is the local runner (OD-170)",
            "",
        ),
    ]
    return rows


def docs_row() -> Row:
    needed = [
        "docs/deployment.md",
        "docs/operations.md",
        "README.md",
        "cji_agent/.env.example",
        "frontend/.env.example",
    ]
    missing = [p for p in needed if not (ROOT / p).is_file()]
    if missing:
        return Row("Deployment documentation", "files exist", "fail", ", ".join(needed), NEXT, f"missing {missing}", "")
    return Row(
        "Deployment documentation",
        "files exist (content checked by test_operations_doc, test_docs)",
        "pass",
        ", ".join(needed[:2]),
        "",
        "",
        "",
    )


def evaluate(ev: Path) -> list[Row]:
    rows = [
        flag_file(
            ev,
            "logs-check.json",
            "Structured logs with correlation IDs",
            "every service line is JSON; one request id links Next.js -> API -> run -> MCP",
        ),
        flag_file(ev, "metrics-check.json", "Metrics", "/metrics scrapes of the API, collector and MCP servers"),
        flag_file(ev, "trace-check.json", "Traces", "cji-trace show: one trace spans >= 3 processes"),
        flag_file(ev, "audit-check.json", "Audit events", "security.jsonl: every action seen, field allow-list holds"),
        tests_row(ev, "Secret management and rotation", r"rotat", 3),
        deps_row(ev),
        secret_row(ev),
        tests_row(ev, "Rate limiting and abuse controls", r"rate_limit|auth_failure|abuse|flood|too_many", 3),
        *drill_rows(ev),
        flag_file(ev, "ops-status.json", "Health and readiness", "cji-ops status --json on the live deployment"),
        recovery_row(ev),
        ci_row(ev),
        flag_file(
            ev,
            "parity-check.json",
            "No regressions: Spec 14 parity",
            "API = CLI --status = checkpoint = last_run.json; API = engine (demo data)",
        ),
        tests_row(ev, "Environment validation", r"production|check_env|check-env", 5),
        docs_row(),
        flag_file(
            ev,
            "canary.json",
            "No sensitive data in logs, reports or client bundles",
            "ci/sensitive_scan.py over logs, audit, reports, databases, bundle, HTTP responses",
        ),
        *owner_rows(),
    ]
    return rows


def render(rows: list[Row], verdict: str, ev: Path) -> str:
    lines = [
        "# Release checklist",
        "",
        "Generated by `python ci/release_check.py` (Spec 15, OD-174). Do not edit by hand: change the evidence and",
        "run it again. Results: `pass` (check ran and passed), `fail` (check failed or has no evidence), `blocked`",
        "(needs the owner), `n/a` (does not apply; reason given). Owner items pass only when recorded in",
        '`ci/owner-evidence.json` (`{"items": {"<key>": {"status": "pass", "evidence": "..."}}}`).',
        "",
        f"Evidence: `{_rel(ev)}`; generated {date.today().isoformat()}.",
        "",
        "| Control | Check | Result | Evidence | Owner | Blocker | Detail |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        cells = [
            r.control,
            r.check,
            f"**{r.result}**",
            f"`{r.evidence}`",
            r.owner or "-",
            r.blocker or "-",
            r.detail or "-",
        ]
        lines.append("| " + " | ".join(c.replace("|", "\\|").replace("\n", " ") for c in cells) + " |")
    lines += ["", f"**{verdict}**", ""]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ci/release_check.py", description=__doc__.split("\n\n")[0])
    parser.add_argument("--evidence", type=Path, default=DEFAULT_EVIDENCE)
    parser.add_argument("--checklist", type=Path, default=ROOT / "docs" / "release-checklist.md")
    parser.add_argument("--json", type=Path, default=ROOT / "ci" / "out" / "release-check.json")
    args = parser.parse_args(argv)
    rows = evaluate(args.evidence)
    failed = sum(r.result == "fail" for r in rows)
    blocked = sum(r.result == "blocked" for r in rows)
    verdict = "READY" if not failed and not blocked else f"NOT READY ({blocked} blocked, {failed} failed)"
    args.checklist.write_text(render(rows, verdict, args.evidence), encoding="utf-8")
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(
        json.dumps({"verdict": verdict, "rows": [asdict(r) for r in rows]}, indent=2), encoding="utf-8"
    )
    for r in rows:
        print(f"{r.result:<8} {r.control:<58} {r.blocker or r.detail}")
    print(verdict)
    return 0 if verdict == "READY" else 1


if __name__ == "__main__":
    raise SystemExit(main())
