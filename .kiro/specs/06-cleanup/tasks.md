# Spec 06 — Dead Code and Documentation Cleanup: Tasks
Sequential. `[x]` means evidence exists. No commits or pushes: each step is recorded as a patch file in `evidence/`.
**Environment:** protected environment (both database URLs point at a dead local port; the Supabase database is
live). Nothing in this Spec connected to Supabase.
**Status:** Spec written 2026-10-28; OD-34 to OD-40 approved with defaults; **implemented and gated 2026-10-28**
(gate run 03:23:20–03:28:03).

## Tasks
- [x] **T0 Prepare.** `evidence/pre-spec06-tracked.patch` and `evidence/pre-spec06-untracked/` (every untracked
  file under `cji_agent/`). Baseline = the Spec 05 gate (409/420, F-01 only), run after the last Spec 05 code change.
- [x] **T1 Inventory and failing tests.** `evidence/t1-inventory.txt` (`git grep` per item, script
  `t1-inventory.py`): `test_dummy` and `ingest_json()` referenced only by their own definitions; `dashboard2` only by
  a style comment; run-log names only by `inspect_schemas.py` (removed). Root diagnostics: `test_server.py` imports
  `CJI_MODE` and `EVENTS_PARQUET` from the journey-data server, which no longer defines them (broken since Spec 05);
  `test_load.py` imports `dashboard` (runs the page against the database); the others import names that still exist.
  `validate_collector_settings` is used only by `test_p0_security.py` as the policy seam; startup applies the same
  check inline (kept). New tests written first: **20/101 passed** before the change (`before-tests-junit.xml`).
- [x] **T2 Removals.** `test_dummy`; `ingest_json()` wrapper; 27 files copied to `evidence/removed/` and deleted
  (`t2-removed.txt`, `scripts/remove_spec06.py`); root `.gitignore`; dashboard style comment.
- [x] **T3 Unused imports and variables.** ruff `F401,F841,F811,F821,E722` over `cji_agent/` (excluding `snippets/`):
  **All checks passed** (`gate-ruff-names.log`). F-12 and F-13 recorded.
- [x] **T4 Exception handling.** Design §3. Silent handlers in app code: 0. Remaining `except Exception` handlers are
  marked `# broad-except: <reason>` (12: four workers, ingestion worker, MCP client ×2, ChromaDB ×3, repository
  conversion, collector batch task; plus the F-07 per-row insert). Enforced by `test_cleanup.py`.
- [x] **T5 Ingestion overwrite and `sys.path`.** Upload and CLI append by default; replace is explicit. Redundant
  `sys.path.insert` removed; the six that remain point at Spec 11. Seeded synthetic data identical on every
  deterministic column to the pre-Spec-06 generator (`gate-synthetic.log`).
- [x] **T6 Documentation.** `README.md` rewritten from the code; banners on 3 superseded and 17 historical documents
  (`t6-banners.txt`, `scripts/banners_spec06.py`); `docs/README.md` index with known divergences; `tenacity` in
  `requirements.txt`.
- [x] **T7 Gate.** Results below; `spec06-tracked.patch`, `spec06-new-files/`, `final-numbers.txt`.

Edits were applied by `scripts/apply_spec06.py` (113 checked edits) and follow-ups `fix_spec06_1.py` … `fix_spec06_5.py`:
an unused `derived` variable; the remaining dashboard loader calls and a SQLAlchemy id read; `OSError` added to the
LLM fallbacks (the existing contract tests disable the network with the built-in `ConnectionError`); lint in the new
tests; and the boundary marker changed from `# noqa: BLE001 - …` to `# broad-except: …`, because BLE001 is not
enabled in this ruff configuration and the `noqa` counted as unused (RUF100).

## Gate results (`evidence/gate-results.txt`, `evidence/final-numbers.txt`)
| Check | Result | Evidence |
|---|---|---|
| Full suite (not integration) | 510/521 pass; the 11 failures are exactly the F-01 set (none new, none fixed) | `gate-pytest-full.log`, `gate-pytest-junit.xml` |
| Spec 06 tests | 101/101 pass (before the change 20/101) | `gate-new-tests.log`, `gate-new-tests-junit.xml` |
| Golden snapshot | identical to Spec 05 | `gate-golden.log`, `golden-after.json` |
| Seeded synthetic data | identical (deterministic columns) to the pre-Spec-06 generator | `gate-synthetic.log` |
| ruff, whole repo | 135 findings (Spec 05: 233) | `gate-ruff.log` |
| ruff unused/undefined names | all checks passed | `gate-ruff-names.log` |
| ruff, new test files | all checks passed | `gate-ruff-new.log` |
| mypy, whole repo | 43 errors in 16 files (Spec 05: 46) | `gate-mypy.log` |
| mypy `--strict repositories` | no issues | `gate-mypy-repositories-strict.log` |
| Static compare per changed file | no changed file worse; `collector/api.py` B608 and `report_server.py` B113 gone | `gate-static-compare.log` |
| Entry points | `main.py --help`, `run_servers.py --help`, `tools/ingest_json.py --help`, `tracker/snippet_generator.py --help`, `python -m settings check`, collector import: all exit 0 | `gate-help-*.log`, `gate-settings-check.log`, `gate-collector-import.log` |
| Dashboard headless (AppTest), database unreachable | renders; one warning names the panels and `OperationalError`; no credentials | `tests/test_dashboard_smoke.py` |
| MCP servers | 8001–8005 listening; all free after stop | `gate-results.txt` |
| Demo pipeline | 8 step metrics, 4 critical steps, report written | `gate-demo-pipeline.log` |
| Ingest probe | file flagged for review, 0 errors | `gate-ingest-probe.log` |
| Mode mismatch | `ModeMismatch` raised | `gate-mode-mismatch.log` |
| `git diff --check` | clean | `gate-diff-check.log` |
| Tracked `events.parquet` | unchanged | `gate-results.txt` |

## Acceptance criteria (requirements §5)
1. **Removed symbols have no remaining references:** met. `test_cleanup.py` greps every removed name and file across
   code, scripts, tests, config, README and `docs/README.md` (planning inputs and `.kiro/specs` excluded) and checks
   the files are gone.
2. **Startup smoke checks and tests pass:** met. Only F-01 fails; the entry-point, server, pipeline, ingest,
   mode-mismatch and headless-dashboard checks pass; golden identical; ruff and mypy lower; no changed file worse.
3. **Documentation matches implemented behaviour:** met. `test_docs.py` checks README flags (`main.py`,
   `run_servers.py`, `tools/ingest_json.py`), collector routes, environment variables, ports and file paths against
   the code, and the banners on every historical document. Every README command class was run by the gate.

## Findings
| ID | Finding | Status / owner |
|---|---|---|
| F-01 | 11 obsolete tests in `test_supervisor.py` | Open: Spec 09, or delete |
| F-02 | `errors` has no reducer | Open: Spec 09 |
| F-03 | Step rates exceed 100 % | Open: Analytics Spec |
| F-04 | Collector/dashboard ports bound by their own launch commands | Open: Spec 11 |
| F-05 | Possible old `cji_live_…` key in Supabase `api_keys` | Open: owner |
| F-07 | Collector per-row insert inside one transaction | Open: Spec 07 (handler marked) |
| F-09 | Dashboard upload replaced `tracking_events` by default | **Fixed (OD-35):** append by default, replace explicit with a warning |
| F-10 | Window arguments ignored by demo queries and realtime `query_events` | Open: Analytics Spec |
| F-11 | `pgserver` test dependency not declared | Open: CI/packaging Spec |
| F-12 | `validate_transformed_data` sends the schema-mapping prompt, not a quality-check prompt | Open: Spec 08 |
| F-13 | Ingestion drops `derived_fields.journey_id` and Hotjar hesitation | Open: Analytics/ingestion Spec |
| F-14 | `snippets/` generated output has an unused import and a broad catch | Open: Spec 07 |
| F-15 | Dashboard data panels need PostgreSQL even in demo mode | Open: Specs 12–14 (now visible as a warning) |
| F-16 | Password-shaped example was in `README.md`; remains in git history | Owner: rotate if real |
| F-17 | `tracker/snippet_generator.py` writes a random `cji_live_…` key into the snippet without registering it, so the collector rejects it (401). Documented in README. | Open: Spec 07 |
| F-18 | `generate_demo_data(seed=…)` is not fully reproducible: ids come from `uuid4()` and timestamps from the clock | Open: Analytics Spec |

## Rollback
No commits exist; restore from the evidence files. Run from the repository root with servers stopped.
1. Tracked files (including the 27 deletions and the doc banners):
   `git apply -R .kiro/specs/06-cleanup/evidence/spec06-tracked.patch`, then
   `git apply .kiro/specs/06-cleanup/evidence/pre-spec06-tracked.patch` (the patches are against `HEAD`; the second
   step restores the Spec 05 state). Deleted files can also be copied back from `evidence/removed/`.
2. Untracked files edited by this Spec (`cji_agent/repositories/duckdb_parquet.py`, `cji_agent/settings/roles.py`):
   copy them from `evidence/pre-spec06-untracked/cji_agent/`.
3. New files: delete `cji_agent/tests/test_cleanup.py`, `cji_agent/tests/test_docs.py`,
   `cji_agent/tests/test_dashboard_smoke.py`, `docs/README.md` and the root `.gitignore`
   (copies in `evidence/spec06-new-files/`).
4. Verify: golden snapshot and full suite should match Spec 05 (409/420, F-01 only).
