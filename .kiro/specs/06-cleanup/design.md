# Spec 06 — Dead Code and Documentation Cleanup: Design

## 1. Removal inventory (OD-34, CL-01, CL-02, CL-10, CL-12)
Each entry is removed only if T1 re-confirms zero references (`git grep -n -w <name>` over the repository, excluding
`.kiro/specs`, `graphify-out`, `refactoring.md`, `kiro_*.md`, `antigravity_*.md`) and the full suite passes after the
removal. Deleted files are copied to `evidence/removed/` before deletion.

| Item | Evidence | Note |
|---|---|---|
| `journey_data_server.test_dummy` | no caller, no test | — |
| `tools/ingest_json.ingest_json()` | no caller; ignores `journey_id_default` | `ingest_file()` is the used entry point (dashboard, CLI, tests) |
| Root `check_parquet.py`, `inspect_schemas.py`, `query_test.py` | no references | one-off diagnostics |
| Root `test_data_server.py`, `test_duckdb_async.py`, `test_load.py`, `test_server.py`, `test_threads.py` | no references; outside `testpaths` | probe the pre-Spec-05 server; T1 records whether each still runs |
| Root logs: `err.log`, `error.log`, `out.log`, `stderr.log`, `main_log.txt`–`main_log5.txt`, `ingest_ga4_log.txt`, `parquet_check.txt`, `schema_report.txt` | run outputs; credential scan 0 hits | new root `.gitignore`: `/*.log`, `/main_log*.txt` |
| `cji_agent/fix.py` | no references | one-off test rewrite, already applied |
| `cji_agent/test_duckdb.py`, `test_pg.py`, `test_servers.py`, `verify_data.py` | no references | `test_servers.py` is superseded by `ping_all_servers` and the gate |
| `cji_agent/test_metadata_query.py` | no references | alters `tracking_events` on the configured database when run |
| `cji_agent/dashboard2.py` | only a style comment in `dashboard.py` | comment updated |

Kept: `generate_diverse.py` (documented: it overwrites `data/events.parquet`, which the golden snapshot reads),
`create_zip.py`, `Team_Contribution_Scripts.zip`, every MCP tool except `test_dummy`, `graph.build_graph(use_persistence)`
(documented compatibility parameter), `collector.api.validate_collector_settings` (T1 checks whether startup calls it;
if not, a finding, not a removal).

## 2. Unused imports and variables (CL-03)
Mechanical removal of the `F401`/`F841` list in requirements §1, by hand (no `ruff --fix`), one file at a time.
Variables that reveal behaviour gaps are removed without changing behaviour and recorded:
- `ingestion_intelligence_server.validate_transformed_data`: `verdict_prompt` is built and never sent; the quality
  check calls the schema-mapping prompt instead (F-12, Spec 08).
- `apply_mapping`: `hint = derived["journey_id"]` is ignored, so `journey_id` is always `imported_journey`;
  `ts_col` unused. `ingest_json._parse_hotjar_sessions`: `delay_ms` (hesitation) parsed and dropped (F-13).
- `synthetic_data`: `fake = Faker()` unused. `Faker.seed()` stays; T5 proves generated data is byte-identical
  (seeded run hashed before and after).
- `report_server.export_report`: `dropoffs` computed, never charted.

## 3. Exception handling (OD-36, CL-04 to CL-09)
| Site | Today | After |
|---|---|---|
| `main.py` console prints (×6) | `try: print(…) except UnicodeEncodeError: pass` or an ASCII re-print | `_configure_console()` at start of `main()`: `stream.reconfigure(errors="replace")` for stdout/stderr when supported; the try/excepts go |
| `main.py` final `aget_state` (×2) | `except Exception: pass` | `except (sqlite3.Error, OSError)`: `[ERROR] final state: <Type>: <msg>` to stderr, exit 1 |
| `main.py` `last_run.json` save | `except Exception` → `[WARN]` | `except (OSError, TypeError, ValueError)` → `[ERROR] last_run.json: …`, exit 1 |
| `dashboard.py` engine creation | `except Exception: engine = None` | `except (sqlalchemy.exc.ArgumentError, ImportError)`: configuration error shown, `engine = None` |
| `dashboard.py` 6 DB loaders | `except Exception: return None` (one prints a traceback) | `except (SQLAlchemyError, PandasDatabaseError) as exc: raise DataLoadError(panel, exc)`; failures are not cached. The shared-data block and the two in-page calls use `_load(panel, fn, *args)`, which collects `DataLoadError`s and renders one `st.warning` listing `panel: Type: message` (message via `repositories.base.describe_failure`, credentials stripped) |
| `dashboard.py` `load_last_run` | `except Exception: return None` | `except (OSError, json.JSONDecodeError)`: warning, `None` |
| `dashboard.py` pipeline launch (×3) | `except Exception: st.error(e)` | `subprocess.TimeoutExpired` (kept) and `OSError` |
| `dashboard.py` upload | `except Exception`; temp-file cleanup `except Exception: pass` | `(ConfigError, ValueError, OSError, SQLAlchemyError)` with the type in the message; cleanup `except OSError` logged |
| `collector/api.py` keep-alive | inner `except Exception` logged; outer `except Exception: pass` | inner `requests.RequestException`; outer removed |
| `collector/api.py` `POST /admin/api-keys` | `except Exception` → 500 with driver text | `ConfigError` → 503 `Database not configured`; `SQLAlchemyError` → logged with `exc_info`, 500 `Database error` |
| `collector/api.py` per-row insert, batch insert | broad | annotated `# broad-except: F-07, replaced in Spec 07`; batch handler re-raises (unchanged) |
| `tools/ingest_json.py` JSON array parse | logs and yields nothing → "No records" | `json.JSONDecodeError` → `ValueError(f"{path}: invalid JSON: {exc}") from exc` |
| `tools/ingest_json.py` existing ids | `except Exception: pass` | `inspect(engine).has_table("tracking_events")`; any other error propagates |
| `tools/ingest_json.py` CLI | `except Exception` | `(ConfigError, ValueError, OSError, SQLAlchemyError)` → `ERR <Type>: <msg>`, exit 1 |
| `tools/synthetic_data.py` upload | `except Exception` logged | `SQLAlchemyError` logged with `exc_info`; Parquet already written (unchanged) |
| `insight_server.generate_insight`, `report_server.generate_narrative`, ingestion LLM providers | `except Exception` → fallback | `(requests.RequestException, KeyError, IndexError, ValueError, TypeError)` → same fallback, logged with `exc_info` |
| `report_server.export_report` write | `except Exception` | `OSError` |
| `ingestion_intelligence_server.apply_mapping` per row | `except (ValidationError, Exception)` | `(ValidationError, ValueError, TypeError)` |
| `validate_transformed_data` LLM verdict | `except Exception` | `(RuntimeError, ValueError, requests.RequestException)` (`_call_llm_for_mapping` raises `RuntimeError` when all providers fail) |
| Workers (×4), `ingestion_worker`, `mcp_client` (×2), ChromaDB (×3), `duckdb_parquet` append | broad, structured result | kept; `# broad-except: <boundary>`; `exc_info=True` added where missing |
| `settings/roles.py` `elif role == "launcher": pass` | no-op branch | comment stating the launcher has no extra requirements |

Policy test (`tests/test_cleanup.py`): walks the AST of every app module (not `tests/`, `snippets/`). Fails on a
broad handler whose `except` line lacks `# broad-except: <reason>`, and on any handler whose body is only
`pass`/`...`/`continue`.

## 4. Ingestion overwrite (OD-35)
```text
ingest_file(input_path, output_path=EVENTS_PARQUET, col_map=None, root_key=None,
            chunk_size=100_000, append=True, replace=False)
  append and replace both true -> ValueError
  replace -> to_sql(if_exists="replace")      # explicit only
  else    -> existing ids from tracking_events (missing table = empty), drop known ids, to_sql(if_exists="append")
  returns (output_path, rows_written)          # signature kept; output_path documented as not written
CLI: --append (default, kept for compatibility) | --replace ; prints "OK <n> events written -> PostgreSQL tracking_events"
Dashboard: checkbox "Replace all rows in tracking_events" + st.warning when ticked; passes replace=<box>
```

## 5. `sys.path.insert` (OD-37)
Removed: `dashboard.py:583` (Streamlit puts the script directory first), `guardrails/output_validator.py`,
`generate_diverse.py`, and the copies in `test_agent_layer.py`, `test_collector_models.py`, `test_friction_engine.py`,
`test_supervisor.py`, `test_synthetic_data.py` (`conftest.py` runs first). Kept, with a comment:
`tests/conftest.py`, `tools/ingest_json.py`, `tools/synthetic_data.py`, `tracker/snippet_generator.py`,
`mcp_servers/friction_engine_server.py`, `mcp_servers/insight_server.py`. A test pins this list.

## 6. Documentation (OD-38, OD-39, CL-13)
- `README.md`: rewrite Quickstart, Demo and Realtime walkthroughs, Environment table, Tests, Security and FAQ from the
  code: `run_servers.py` first, then `main.py`; collector `POST /collect/batch`, `GET /health`, `GET /tracker.js`,
  `GET /live/stats`, `POST /admin/api-keys`; per-journey tracker keys; settings defaults; `CJI_ENV`; both database
  URLs; ports from the registry; `python -m settings`; Chart.js; upload append/replace; no test counts. Sections that
  are still right (guardrails, LangSmith) stay.
- Banners (first lines, body unchanged):
  `> **Superseded (2026-10-28).** Historical record. Current behaviour: README.md; change history: .kiro/specs/.`
  `> **Historical design reference (v2.0, March 2026).** Where this differs from the code, the code and README.md win. Known divergences: docs/README.md.`
- `docs/README.md`: table of every document with status (current / historical / superseded) and the known divergences
  (storage, MCP transport and ports, LLM access, configuration, test layout, report library).
- `tests/test_docs.py`: README `python main.py` flags ⊆ `main.py` argparse flags; HTTP routes ⊆ `collector.api.app`
  routes; environment names in the table ⊆ `settings.load.KNOWN_KEYS`; ports ⊆ service registry; backticked paths
  exist; banners present; no `Sovan`.

## 7. Tests and smoke checks
New: `tests/test_cleanup.py` (removed symbols and files, MCP tool list, handler policy, `sys.path` allow-list,
console reconfiguration, ingest append/replace/missing-table/JSON error with an in-memory SQLite engine, collector
admin-key 500/503 with a fake engine), `tests/test_docs.py`, `tests/test_dashboard_smoke.py` (AppTest with a dead
database URL: no exception, warning names the panels). Gate: Spec 05 gate plus F401/F841 count, `--help` smoke
commands, `python -m settings`, seeded synthetic-data hash, and `git grep` for each removed name.

## 8. Risks
| Risk | Mitigation |
|---|---|
| A narrowed handler meets an unlisted exception and a tool now fails instead of degrading | The next boundary (worker, MCP client) still converts it; the demo pipeline and ingest probe run in the gate |
| AppTest cannot run `dashboard.py` headless | Fallback: import-free AST checks plus a `streamlit run --server.headless` start and HTTP 200 probe |
| Deleted file still used outside the repository | All are tracked; `evidence/removed/` copies; restore with `git checkout HEAD -- <file>` |
| Changing the upload default surprises a user who relied on replace | Replace remains one checkbox or `--replace` away; README and the UI say so |

## 9. Rollback
`git apply -R evidence/spec06-tracked.patch`, then `git apply evidence/pre-spec06-tracked.patch`; restore deleted
files with `git checkout HEAD -- <files>` or from `evidence/removed/`; restore untracked files from
`evidence/pre-spec06-untracked/`; delete the new test files, `docs/README.md` and the root `.gitignore`.
