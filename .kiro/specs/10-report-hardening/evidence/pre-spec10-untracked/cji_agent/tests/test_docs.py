"""
Spec 06 (CL-13): README.md must describe the code as it is, and historical
documents must say that they are historical.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from settings import KNOWN_KEYS, SERVICE_NAMES, get_settings

APP_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = APP_ROOT.parent
README = (REPO_ROOT / "README.md").read_text(encoding="utf-8")

SUPERSEDED = ["Project_Memory.md", "Project_status.md", "docs/development_status.md"]
HISTORICAL = sorted(
    str(p.relative_to(REPO_ROOT)).replace("\\", "/")
    for p in [*(REPO_ROOT / "docs").glob("*.md"), *(REPO_ROOT / "Project Details").glob("*.md")]
    if p.name not in {"README.md", "development_status.md"}
)


def _argparse_flags(path: Path) -> set[str]:
    return set(re.findall(r'add_argument\(\s*"(--[\w-]+)"', path.read_text(encoding="utf-8")))


def _readme_flags(script: str) -> set[str]:
    flags: set[str] = set()
    for line in README.splitlines():
        if f"python {script}" in line:
            tail = line.split(f"python {script}", 1)[1]
            flags |= set(re.findall(r"(?<![\w-])(--[a-z][\w-]*)", tail))
    return flags


@pytest.mark.parametrize("script", ["main.py", "run_servers.py", "tools/ingest_json.py"])
def test_readme_uses_only_real_cli_flags(script):
    used = _readme_flags(script)
    real = _argparse_flags(APP_ROOT / script) | {"--help"}
    assert used <= real, f"README flags not in {script}: {sorted(used - real)}"


def test_readme_routes_exist():
    from collector import api

    real = {route.path for route in api.app.routes}
    used = set(re.findall(r"`(?:GET|POST|PUT|DELETE) (/[\w./-]*)`", README))
    assert used, "README should list the collector routes"
    assert used <= real, f"README routes not served by collector.api: {sorted(used - real)}"


def test_readme_environment_variables_exist():
    rows = re.findall(r"^\|\s*`([A-Z][A-Z0-9_]+)`\s*\|", README, re.MULTILINE)
    assert rows, "README should have an environment-variable table"
    unknown = sorted(set(rows) - set(KNOWN_KEYS))
    assert unknown == [], f"README documents variables settings do not read: {unknown}"


def test_readme_documents_required_settings():
    rows = set(re.findall(r"^\|\s*`([A-Z][A-Z0-9_]+)`\s*\|", README, re.MULTILINE))
    for name in ["CJI_ENV", "CJI_MODE", "DATABASE_URL", "SUPABASE_DATABASE_URL", "CJI_ADMIN_KEY", "JOURNEY_NAME", "LLM_MODEL"]:
        assert name in rows, f"README environment table is missing {name}"


def test_readme_ports_come_from_the_service_registry():
    services = get_settings().services
    registry = {services.get(name).port for name in SERVICE_NAMES}
    used = {int(p) for p in re.findall(r"(?:localhost:|127\.0\.0\.1:|--port |port )(\d{4})\b", README)}
    used |= {int(p) for p in re.findall(r"^\|\s*(\d{4})\s*\|", README, re.MULTILINE)}
    assert used, "README should state the ports"
    assert used <= registry, f"README ports not in the registry: {sorted(used - registry)}"


RUNTIME_PREFIXES = ("data/", "reports/", ".venv")


def test_readme_paths_exist():
    missing = []
    for token in set(re.findall(r"`([\w./-]+\.(?:py|md|js|json|txt|ini|example|parquet|html))`", README)):
        if token.startswith(RUNTIME_PREFIXES) or token.startswith("/") or "<" in token:
            continue
        if not any((base / token).exists() for base in (REPO_ROOT, APP_ROOT, APP_ROOT / "tracker")):
            missing.append(token)
    assert missing == [], f"README refers to files that do not exist: {sorted(missing)}"


def test_readme_has_no_password_shaped_example():
    assert "Sovan" not in README
    assert "113" not in README          # stale test count
    assert "--output-mode" not in README


def test_readme_starts_the_mcp_servers_before_the_pipeline():
    start = README.index("python run_servers.py")
    assert start < README.index("python main.py --mode demo --run")


@pytest.mark.parametrize("rel", SUPERSEDED)
def test_superseded_documents_say_so(rel):
    first = (REPO_ROOT / rel).read_text(encoding="utf-8-sig").lstrip().splitlines()[0]
    assert first.startswith("> **Superseded"), f"{rel}: {first[:80]}"


@pytest.mark.parametrize("rel", HISTORICAL)
def test_historical_design_documents_say_so(rel):
    first = (REPO_ROOT / rel).read_text(encoding="utf-8-sig").lstrip().splitlines()[0]
    assert first.startswith("> **Historical design reference"), f"{rel}: {first[:80]}"


def test_docs_index_lists_every_document():
    index = (REPO_ROOT / "docs" / "README.md").read_text(encoding="utf-8")
    for rel in [*SUPERSEDED, *HISTORICAL]:
        assert Path(rel).name in index, f"docs/README.md does not list {rel}"
