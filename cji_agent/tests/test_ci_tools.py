"""
Spec 15 (OD-170, OD-173, OD-174): the repository's CI tools — ratchet parsing of ci/run_ci.py, the canary scan
and the release check's verdicts. Offline; temporary directories only.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

CI = Path(__file__).resolve().parents[2] / "ci"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"ci_{name}", CI / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses look their module up while the class is created
    spec.loader.exec_module(module)
    return module


run_ci = _load("run_ci")
sensitive = _load("sensitive_scan")
release = _load("release_check")


# ── ratchets ─────────────────────────────────────────────────────────────────────────────────────────────
def test_ruff_ratchet_counts_findings():
    assert run_ci.ruff_check(1, "x\nFound 92 errors.\n")[0] is True
    assert run_ci.ruff_check(1, "Found 93 errors.")[0] is False
    assert run_ci.ruff_check(0, "All checks passed!")[0] is True
    assert run_ci.ruff_check(2, "crash")[0] is False  # no count: never a pass


def test_mypy_ratchet_and_strict_set():
    assert run_ci.mypy_ratchet(1, "Found 33 errors in 11 files (checked 200 source files)")[0] is True
    assert run_ci.mypy_ratchet(1, "Found 34 errors in 11 files (checked 200 source files)")[0] is False
    assert run_ci.mypy_clean(0, "Success: no issues found in 40 source files")[0] is True
    assert run_ci.mypy_clean(1, "Found 1 error in 1 file")[0] is False


def test_bandit_ratchet_reads_severity_totals():
    def report(low, med, high):
        totals = {"SEVERITY.LOW": low, "SEVERITY.MEDIUM": med, "SEVERITY.HIGH": high}
        return "[main] INFO\n" + json.dumps({"metrics": {"_totals": totals}})

    assert run_ci.bandit_check(1, report(25, 10, 0))[0] is True
    assert run_ci.bandit_check(1, report(25, 10, 1))[0] is False
    assert run_ci.bandit_check(1, report(26, 0, 0))[0] is False
    assert run_ci.bandit_check(1, "not json")[0] is False


def test_protected_environment_has_dead_endpoints_and_no_real_database():
    env = run_ci.protected_env()
    assert env["HTTPS_PROXY"] == "http://127.0.0.1:9"
    assert env["DATABASE_URL"] == env["SUPABASE_DATABASE_URL"] == run_ci.DEAD_DB
    assert env["CJI_LLM_PROVIDER"] == "none"
    assert "CJI_HOME" not in env and "CJI_TEST_DATABASE_URL" not in env


def test_formatted_list_names_existing_python_files():
    files = run_ci.formatted_files()
    root = CI.parent
    assert files and all(f.endswith(".py") and (root / f).is_file() for f in files)


# ── canary scan ──────────────────────────────────────────────────────────────────────────────────────────
def _markers(tmp_path: Path) -> Path:
    path = tmp_path / "markers.json"
    path.write_text(
        json.dumps(
            {"secret": {"admin_key": "cjicanaryadmin" + "a" * 32}, "user": {"user_id": "cjicanaryuser" + "b" * 32}}
        ),
        encoding="utf-8",
    )
    return path


def test_canary_scan_flags_secret_markers_anywhere(tmp_path, capsys):
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "api.log").write_text("ok line\nkey=cjicanaryadmin" + "a" * 32 + "\n", encoding="utf-8")
    report = tmp_path / "canary.json"
    code = sensitive.main(["--markers", str(_markers(tmp_path)), "--paths", str(logs), "--report", str(report)])
    assert code == 1
    data = json.loads(report.read_text(encoding="utf-8"))
    assert data["ok"] is False and data["violations"]
    assert "a" * 32 not in capsys.readouterr().out + report.read_text(encoding="utf-8")  # values never printed


def test_canary_scan_allows_user_markers_only_where_listed(tmp_path):
    store = tmp_path / "data" / "ingestion_uploads"
    store.mkdir(parents=True)
    (store / "upload.csv").write_bytes(("u," + "cjicanaryuser" + "b" * 32).encode("utf-16-le"))
    other = tmp_path / "reports"
    other.mkdir()
    (other / "r.html").write_text("<p>clean</p>", encoding="utf-8")
    args = ["--markers", str(_markers(tmp_path)), "--paths", str(store), str(other)]
    assert sensitive.main([*args, "--user-allowed", "*/data/ingestion_uploads/*"]) == 0
    assert sensitive.main(args) == 1  # the same file without the allowance is a violation


def test_canary_scan_refuses_short_markers(tmp_path):
    path = tmp_path / "m.json"
    path.write_text(json.dumps({"secret": {"k": "short"}}), encoding="utf-8")
    assert sensitive.main(["--markers", str(path), "--paths", str(tmp_path)]) == 2


# ── release check ────────────────────────────────────────────────────────────────────────────────────────
def test_release_check_without_evidence_fails_every_engineering_control(tmp_path):
    rows = release.evaluate(tmp_path)
    by = {r.control: r for r in rows}
    assert by["Structured logs with correlation IDs"].result == "fail"
    assert by["Failure injection and recovery"].result == "fail"
    assert by["Container scanning"].result == "n/a" and by["Container scanning"].owner
    assert all(r.owner and r.blocker for r in rows if r.result in ("fail", "blocked", "n/a"))


def test_release_check_reports_not_ready_while_owner_items_block(tmp_path):
    checklist = tmp_path / "checklist.md"
    code = release.main(
        ["--evidence", str(tmp_path), "--checklist", str(checklist), "--json", str(tmp_path / "r.json")]
    )
    assert code == 1
    text = checklist.read_text(encoding="utf-8")
    assert "**NOT READY (" in text and "| Owner |" in text


def test_dependency_advisories_without_exception_block_the_release(tmp_path):
    (tmp_path / "ci").mkdir()
    (tmp_path / "ci" / "deps.json").write_text(
        json.dumps(
            {
                "advisories": [{"package": "langgraph", "version": "0.2.28", "id": "GHSA-x", "status": "open"}],
                "errors": [],
            }
        ),
        encoding="utf-8",
    )
    row = release.deps_row(tmp_path)
    assert row.result == "blocked" and "langgraph 0.2.28" in row.blocker and row.owner == release.OWNER


@pytest.mark.parametrize("ok, expected", [(True, "pass"), (False, "fail")])
def test_flag_files_map_to_results(tmp_path, ok, expected):
    (tmp_path / "logs-check.json").write_text(json.dumps({"ok": ok, "detail": "d"}), encoding="utf-8")
    assert release.flag_file(tmp_path, "logs-check.json", "Logs", "check").result == expected
