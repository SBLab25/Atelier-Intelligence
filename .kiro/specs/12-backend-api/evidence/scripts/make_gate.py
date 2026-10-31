"""Write gate_spec12.ps1 from the Spec 11 gate (same phases and checks) plus the Spec 12 steps.

Every replacement must match exactly once, so a change in the Spec 11 gate cannot be skipped silently.
"""
from __future__ import annotations

from pathlib import Path

HERE = Path(__file__).resolve().parent
SPEC11 = HERE.parents[2] / "11-packaging" / "evidence" / "scripts" / "gate_spec11.ps1"
OUT = HERE / "gate_spec12.ps1"

text = SPEC11.read_text(encoding="utf-8")


def rep(old: str, new: str) -> None:
    global text
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"expected one match, found {count}: {old[:80]!r}")
    text = text.replace(old, new)


rep("# Spec 11 gate (T6/T7): build and clean-install proof (design §7, OD-106), then the Spec 10 gate on the packaged code.",
    "# Spec 12 gate (T8): the Spec 11 gate (build, clean install, Spec 10 gate on the packaged code) plus the /api/v1 checks:\n"
    "# the installed cji-api against the gate's runs and reports, the OpenAPI snapshot, cji-settings check --role api.")
rep('$ev   = Join-Path $repo ".kiro\\specs\\11-packaging\\evidence"',
    '$ev   = Join-Path $repo ".kiro\\specs\\12-backend-api\\evidence"\n'
    '$ev11 = Join-Path $repo ".kiro\\specs\\11-packaging\\evidence"')
rep('$tmp  = "C:\\Users\\sovan\\.kiro\\s11_gate_tmp"', '$tmp  = "C:\\Users\\sovan\\.kiro\\s12_gate_tmp"')
rep('"Spec 11 gate started $(Get-Date -Format s)"', '"Spec 12 gate started $(Get-Date -Format s)"')
rep('Note "Spec 11 gate finished $(Get-Date -Format s)"', 'Note "Spec 12 gate finished $(Get-Date -Format s)"')
# Spec 11 helper scripts are reused from their evidence folder; the wheel check has the two new scripts.
for name in ("golden.py", "audit_check.py", "audit_workflow_check.py", "report_contract_check.py"):
    rep(f'(Join-Path $ev "scripts\\{name}")', f'(Join-Path $ev11 "scripts\\{name}")')
rep('foreach ($s in "cji","cji-servers","cji-settings","cji-dashboard","cji-collector","cji-ingest-json","cji-snippet","cji-generate-diverse") {',
    'foreach ($s in "cji","cji-servers","cji-settings","cji-dashboard","cji-collector","cji-ingest-json","cji-snippet","cji-generate-diverse","cji-api","cji-api-token") {')
rep('''Step "pytest Spec 11 tests" "gate-new-tests.log" {
    & $py -m pytest tests/test_packaging.py tests/test_cleanup.py tests/test_docs.py tests/test_settings.py tests/test_contracts.py `
        tests/test_dashboard_smoke.py tests/test_workflow.py -p no:cacheprovider -m "not integration" -rfEs $junitNew
}''', '''Step "pytest Spec 12 tests" "gate-new-tests.log" {
    & $py -m pytest tests/test_api_contract.py tests/test_api_units.py tests/test_packaging.py tests/test_docs.py `
        tests/test_settings.py tests/test_cleanup.py tests/test_friction_engine.py tests/test_workflow.py `
        tests/test_dashboard_smoke.py tests/test_repositories.py -p no:cacheprovider -m "not integration" -rfEs $junitNew
}
Step "OpenAPI snapshot matches the app" "gate-openapi-snapshot.log" { & $py -m cji.api.openapi_snapshot --check }''')
rep('''$g10 = (Get-FileHash (Join-Path $ev10 "golden-after.json")).Hash
$g11 = (Get-FileHash (Join-Path $ev "golden-after.json")).Hash
Note "golden identical to Spec 10: $($g10 -eq $g11)"''', '''$g11 = (Get-FileHash (Join-Path $ev11 "golden-after.json")).Hash
$g12 = (Get-FileHash (Join-Path $ev "golden-after.json")).Hash
Note "golden identical to Spec 11 (friction scoring moved to cji.analytics): $($g11 -eq $g12)"''')
rep('''        tools/ingest_json.py tracker/snippet_generator.py settings collector src/cji/logs.py src/cji/dashboard_launcher.py `
        src/cji/collector/serve.py src/cji/__init__.py src/cji/tracker/__init__.py tests/test_packaging.py''',
    '''        tools/ingest_json.py tracker/snippet_generator.py settings collector src/cji/api src/cji/services src/cji/analytics `
        src/cji/http src/cji/workflow/index.py src/cji/collector/middleware.py tests/test_api_contract.py tests/test_api_units.py `
        tests/_api_harness.py tests/test_packaging.py''')
rep('$py -m mypy --cache-dir "C:\\Users\\sovan\\.kiro\\s11_mypy_cache" }',
    '$py -m mypy --cache-dir "C:\\Users\\sovan\\.kiro\\s12_mypy_cache" }')
rep('''    & $py -m mypy src/cji/logs.py src/cji/dashboard_launcher.py src/cji/collector/serve.py src/cji/settings/load.py --strict --follow-imports=silent --cache-dir "C:\\Users\\sovan\\.kiro\\s11_mypy_cache"''',
    '''    & $py -m mypy src/cji/api src/cji/services src/cji/analytics src/cji/http src/cji/workflow/index.py --strict --follow-imports=silent --cache-dir "C:\\Users\\sovan\\.kiro\\s12_mypy_cache"''')
text = text.replace('--cache-dir "C:\\Users\\sovan\\.kiro\\s11_mypy_cache"', '--cache-dir "C:\\Users\\sovan\\.kiro\\s12_mypy_cache"')
rep('Step "python -m settings check (cli)" "gate-settings-check.log" { & $py -m settings check --no-dotenv }',
    '''Step "python -m settings check (cli)" "gate-settings-check.log" { & $py -m settings check --no-dotenv }
Step "cji-settings check --role api (https origin, cursor secret)" "gate-settings-api.log" {
    $env:CJI_API_CORS_ORIGINS = "https://app.example.test"; $env:CJI_API_CURSOR_SECRET = "gate-only-cursor-secret-0123456789abcdef"
    & (Join-Path (Split-Path $py) "cji-settings.exe") check --role api --no-dotenv; $c = $LASTEXITCODE
    Remove-Item Env:CJI_API_CORS_ORIGINS, Env:CJI_API_CURSOR_SECRET; $global:LASTEXITCODE = $c
}
Step "cji-settings check --role api refuses production defaults (exit 2)" "gate-settings-api-refused.log" {
    & (Join-Path (Split-Path $py) "cji-settings.exe") check --role api --no-dotenv; $c = $LASTEXITCODE
    "exit=$c"; $global:LASTEXITCODE = [int]($c -ne 2)
}''')
rep('''Note "report files for the approved run: $reportsForPaused"''',
    '''Note "report files for the approved run: $reportsForPaused"
Step "pause a run for the API" "gate-pause-api.log" { & $py main.py --mode demo --run }
$pausedApi = ThreadId "gate-pause-api.log"
Note "paused thread for the API: $pausedApi"
Step "cji-api live: auth, data, runs, approval, reports, problems" "gate-api-live.log" {
    & $py (Join-Path $ev "scripts\\api_live_check.py") (Split-Path $py) $app (Join-Path $tmp "api") $pausedApi
}
Note "ports after cji-api: $(Listening @(8006))"
Step "CLI status of the run approved through the API" "gate-status-api.log" { & $py main.py --status --thread-id $pausedApi }''')
rep('Copy-Item (Join-Path $home11 "reports") (Join-Path $ev "gate-clean-home-reports") -Recurse -ErrorAction SilentlyContinue',
    'Copy-Item (Join-Path $home11 "reports") (Join-Path $ev "gate-clean-home-reports") -Recurse -ErrorAction SilentlyContinue\n'
    'Copy-Item (Join-Path $tmp "api\\cji-api.log") (Join-Path $ev "gate-api-server.log") -ErrorAction SilentlyContinue')
OUT.write_text(text, encoding="utf-8", newline="\r\n")
print(f"wrote {OUT}")
