"""
Spec 06 code edits (T2-T5). Every edit names the exact text it replaces and how
many times it must occur; if any edit does not match, nothing is written.

    python apply_spec06.py            # check and apply
    python apply_spec06.py --check    # check only
"""
from __future__ import annotations

import pathlib
import re
import sys

APP = pathlib.Path(__file__).resolve().parents[5] / "cji_agent"
EDITS: dict[str, list[tuple[str, str, str, int]]] = {}


def lit(rel: str, old: str, new: str, count: int = 1) -> None:
    EDITS.setdefault(rel, []).append(("lit", old, new, count))


def rx(rel: str, pattern: str, new: str, count: int = 1) -> None:
    EDITS.setdefault(rel, []).append(("rx", pattern, new, count))


# ── journey_data_server: test_dummy (CL-02) ──────────────────────────────────
J = "mcp_servers/journey_data_server.py"
lit(J, '''@mcp.tool()
def test_dummy(val: int = 10) -> dict:
    return {"val": val, "worked": True}

@mcp.tool()
async def get_system_info''', '''@mcp.tool()
async def get_system_info''')

# ── graph.py: unused imports ─────────────────────────────────────────────────
G = "graph.py"
lit(G, '''import logging
import sqlite3
from typing import Optional

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.sqlite import SqliteSaver

from config import CHECKPOINTS_DB
from state import CJIState''', '''import logging

from langgraph.graph import StateGraph, START, END

from state import CJIState''')

# ── main.py (CL-07) ──────────────────────────────────────────────────────────
M = "main.py"
lit(M, '''import argparse
import os
import sys
from datetime import datetime
from pathlib import Path
from uuid import uuid4''', '''import argparse
import os
import sqlite3
import sys
from datetime import datetime
from uuid import uuid4''')
lit(M, '''def main() -> int:
    """Main entry point. Returns exit code (0 = success, 1 = error)."""
    args = _parse_args()
''', '''def _configure_console(*streams) -> None:
    """Print characters the console cannot encode as '?' instead of failing (e.g. cp1252 consoles)."""
    for stream in streams or (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(errors="replace")


def main() -> int:
    """Main entry point. Returns exit code (0 = success, 1 = error, 2 = configuration error)."""
    args = _parse_args()
    _configure_console()
''')
lit(M, '''            JOURNEY_CONFIG,
            FRICTION_SCORE_THRESHOLD,
            logger,
        )''', '''            JOURNEY_CONFIG,
        )''')
lit(M, r'''                        try:
                            print(f"  {icon} {last['worker']}: {last['message']}")
                        except UnicodeEncodeError:
                            print(f"  {icon} {last['worker']}: {last['message'].encode('ascii', 'replace').decode('ascii')}")''',
    r'''                        print(f"  {icon} {last['worker']}: {last['message']}")''', 2)
lit(M, r'''                        try:
                            print(f"  [WARN] {msg}")
                        except UnicodeEncodeError:
                            print(f"  [WARN] {str(msg).encode('ascii', 'replace').decode('ascii')}")''',
    r'''                        print(f"  [WARN] {msg}")''')
lit(M, r'''                        try:
                            print(f"\n[PAUSED] Analysis paused - {len(event['insights'])} insights ready for review.")
                            print(f"  Run to approve and generate report:")
                            print(f"  python main.py --approve --thread-id {thread_id}")
                        except UnicodeEncodeError:
                            pass
                        paused = True''', r'''                        print(f"\n[PAUSED] Analysis paused - {len(event['insights'])} insights ready for review.")
                        print("  Run to approve and generate report:")
                        print(f"  python main.py --approve --thread-id {thread_id}")
                        paused = True''')
lit(M, '''                        report = final_state.get("report_path", "")
                    except Exception:
                        pass
''', '''                        report = final_state.get("report_path", "")
                    except (sqlite3.Error, OSError) as exc:
                        print(f"[ERROR] final state: {type(exc).__name__}: {exc}", file=sys.stderr)
                        return 1
''')
lit(M, '''                    except Exception as _e:
                        print(f"  [WARN] Could not save last_run.json: {_e}")''', '''                    except (OSError, TypeError, ValueError) as exc:
                        print(f"[ERROR] last_run.json: {type(exc).__name__}: {exc}", file=sys.stderr)
                        return 1''')
lit(M, r'''                    if report:
                        try:
                            print(f"\n[DONE] Report generated -> {report}")
                        except UnicodeEncodeError:
                            pass
                    else:
                        try:
                            print("\n[DONE] Analysis complete.")
                        except UnicodeEncodeError:
                            pass
''', r'''                    if report:
                        print(f"\n[DONE] Report generated -> {report}")
                    else:
                        print("\n[DONE] Analysis complete.")
''')
lit(M, '''        asyncio.run(run_analysis())
        return 0''', '''        return asyncio.run(run_analysis()) or 0''')
lit(M, r'''                try:
                    snap   = await graph.aget_state(config)
                    report = snap.values.get("report_path", "")
                    if report:
                        try:
                            print(f"\n[DONE] Report generated -> {report}")
                        except UnicodeEncodeError:
                            pass
                except Exception:
                    pass
''', r'''                try:
                    snap = await graph.aget_state(config)
                except (sqlite3.Error, OSError) as exc:
                    print(f"[ERROR] final state: {type(exc).__name__}: {exc}", file=sys.stderr)
                    return 1
                report = snap.values.get("report_path", "")
                if report:
                    print(f"\n[DONE] Report generated -> {report}")
                return 0
''')
lit(M, '''        asyncio.run(resume_analysis())
        return 0''', '''        return asyncio.run(resume_analysis()) or 0''')

# ── collector/api.py (CL-09) ─────────────────────────────────────────────────
C = "collector/api.py"
lit(C, '''from sqlalchemy import create_engine, text
from fastapi import FastAPI, BackgroundTasks, HTTPException, Header, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse''', '''from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from fastapi import FastAPI, BackgroundTasks, HTTPException, Header, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse''')
lit(C, "from settings.model import DEV_TRACKER_KEY, KNOWN_DEFAULT_ADMIN_KEYS, MIN_ADMIN_KEY_LENGTH",
    "from settings.model import DEV_TRACKER_KEY, KNOWN_DEFAULT_ADMIN_KEYS")
lit(C, '''    except Exception as e:
        logger.error(f"Keep-alive ping failed: {e}")''', '''    except requests.RequestException as e:
        logger.error(f"Keep-alive ping failed: {type(e).__name__}: {e}")''')
lit(C, '''        try:
            await asyncio.to_thread(_ping_keepalive, url)
        except Exception:
            pass
        await asyncio.sleep(interval_s)''', '''        await asyncio.to_thread(_ping_keepalive, url)
        await asyncio.sleep(interval_s)''')
lit(C, '''                except Exception as e:
                    logger.error(f"Error inserting event {event.event_id}: {e}")''',
    '''                except Exception as e:  # noqa: BLE001 - F-07: per-row insert, replaced in Spec 07
                    logger.error(f"Error inserting event {event.event_id}: {e}")''')
lit(C, '''    except Exception as e:
        logger.error(f"Batch insert failed: {e}")
        raise e''', '''    except Exception as e:  # noqa: BLE001 - background-task boundary: logged with cause, re-raised
        logger.error(f"Batch insert failed: {e}", exc_info=True)
        raise''')
lit(C, '''    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")''', '''    except ConfigError as exc:
        raise HTTPException(status_code=503, detail="Database not configured") from exc
    except SQLAlchemyError as exc:
        logger.error("API key insert failed: %s", type(exc).__name__, exc_info=True)
        raise HTTPException(status_code=500, detail="Database error") from exc''')

# ── ingestion_intelligence_server.py ─────────────────────────────────────────
I = "mcp_servers/ingestion_intelligence_server.py"
lit(I, '''import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, get_args

import duckdb
import pandas as pd''', '''import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import get_args

import pandas as pd''')
lit(I, '''    ANTHROPIC_API_KEY,
    CJI_MODE,
    DATA_DIR,
    DUCKDB_PATH,
    GROQ_API_KEY,''', '''    ANTHROPIC_API_KEY,
    GROQ_API_KEY,''')
lit(I, '''    LLM_MODEL,
    logger,
)''', '''    LLM_MODEL,
)''')
LLM_ERRORS = "(requests.RequestException, KeyError, IndexError, ValueError, TypeError)"
lit(I, '''        except Exception as e:
            errors.append(f"Anthropic failed: {e}")''', f'''        except {LLM_ERRORS} as e:
            errors.append(f"Anthropic failed: {{type(e).__name__}}: {{e}}")''')
lit(I, '''        except Exception as e:
            errors.append(f"Groq failed: {e}")''', f'''        except {LLM_ERRORS} as e:
            errors.append(f"Groq failed: {{type(e).__name__}}: {{e}}")''')
lit(I, '''        hint = derived.get("journey_id", "")
        df["journey_id"] = "imported_journey"''', '''        df["journey_id"] = "imported_journey"   # F-13: derived_fields["journey_id"] is not applied''')
lit(I, '''        ts_col = df["timestamp"].astype(str)
''', '')
lit(I, "        except (ValidationError, Exception) as e:", "        except (ValidationError, ValueError, TypeError) as e:")
rx(I, r'            verdict_prompt = f"""Review this sample.*?Note any concerns\."""\n',
   '            # F-12: the quality check reuses the schema-mapping prompt (Spec 08).\n')
lit(I, '''        except Exception:
            llm_verdict = "LLM quality check unavailable''', '''        except (RuntimeError, ValueError, requests.RequestException):
            llm_verdict = "LLM quality check unavailable''')

# ── insight_server.py ────────────────────────────────────────────────────────
N = "mcp_servers/insight_server.py"
lit(N, "from typing import Dict, Any, List, Union", "from typing import Union")
lit(N, '''from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))''', '''from pathlib import Path
# Script entry (python mcp_servers/insight_server.py) until Spec 11 (R-14) packaging.
sys.path.insert(0, str(Path(__file__).parent.parent))''')
lit(N, '''    except Exception as e:
        logger.error(f"LLM generation failed: {e}")''', f'''    except {LLM_ERRORS} as e:
        logger.error(f"LLM generation failed: {{type(e).__name__}}: {{e}}", exc_info=True)''')
lit(N, '''    except Exception as e:
        logger.error(f"Failed to save insight to ChromaDB: {e}")''', '''    except Exception as e:  # noqa: BLE001 - vector-store boundary: structured error result
        logger.error(f"Failed to save insight to ChromaDB: {e}", exc_info=True)''')
lit(N, '''    except Exception as e:
        logger.error(f"ChromaDB search failed: {e}")''', '''    except Exception as e:  # noqa: BLE001 - vector-store boundary: structured error result
        logger.error(f"ChromaDB search failed: {e}", exc_info=True)''')
lit(N, '''    except Exception as e:
        logger.error(f"Failed to rank fixes: {e}")''', '''    except Exception as e:  # noqa: BLE001 - vector-store boundary: structured error result
        logger.error(f"Failed to rank fixes: {e}", exc_info=True)''')

# ── report_server.py ─────────────────────────────────────────────────────────
R = "mcp_servers/report_server.py"
lit(R, '''import requests
from pathlib import Path
from typing import Dict, Any, List

from fastmcp''', '''import requests

from fastmcp''')
lit(R, '''    except Exception as e:
        logger.error(f"Narrative generation failed: {e}")''', f'''    except {LLM_ERRORS} as e:
        logger.error(f"Narrative generation failed: {{type(e).__name__}}: {{e}}", exc_info=True)''')
lit(R, "    dropoffs = [step.get('drop_off_pct', 0) for step in funnel_data]\n", "")
lit(R, '''    except Exception as e:
        logger.error(f"Failed to export report: {e}")''', '''    except OSError as e:
        logger.error(f"Failed to export report: {e}", exc_info=True)''')

# ── friction_engine_server.py ────────────────────────────────────────────────
F = "mcp_servers/friction_engine_server.py"
lit(F, '''import json
import sys
from itertools import combinations
from pathlib import Path
from typing import Any

from fastmcp import FastMCP

# Allow running as: python mcp_servers/friction_engine_server.py
''', '''import sys
from itertools import combinations
from pathlib import Path

from fastmcp import FastMCP

# Allow running as: python mcp_servers/friction_engine_server.py (until Spec 11 (R-14) packaging)
''')

# ── agents and MCP client: documented boundaries ─────────────────────────────
W = "agents/workers.py"
lit(W, "import json\nimport logging\n", "import logging\n")
for worker in ("data_worker", "friction_worker", "insight_worker", "report_worker"):
    lit(W, f'''    except Exception as exc:
        logger.error(f"{worker} failed: {{exc}}", exc_info=True)''', f'''    except Exception as exc:  # noqa: BLE001 - worker boundary: recorded as a WorkflowError in state
        logger.error(f"{worker} failed: {{exc}}", exc_info=True)''')
lit("agents/ingestion_worker.py", '''        except Exception as e:
            log.error(f"ingestion_worker error for {file_path}: {e}")''', '''        except Exception as e:  # noqa: BLE001 - worker boundary: recorded per file in state errors
            log.error(f"ingestion_worker error for {file_path}: {e}", exc_info=True)''')
lit("tools/mcp_client.py", '''    except Exception as e:
        # Re-raise as RuntimeError so worker outer try/except catches it''', '''    except Exception as e:  # noqa: BLE001 - MCP call boundary: re-raised as RuntimeError with the cause
        # Re-raise as RuntimeError so worker outer try/except catches it''')
lit("tools/mcp_client.py", '''        except Exception as e:
            logger.error(f"Failed to connect to {name}: {e}")''', '''        except Exception as e:  # noqa: BLE001 - connection boundary: re-raised as RuntimeError with the cause
            logger.error(f"Failed to connect to {name}: {e}")''')
lit("repositories/duckdb_parquet.py", "        except Exception as exc:  # any failure leaves the file untouched",
    "        except Exception as exc:  # noqa: BLE001 - repository boundary: file untouched, re-raised as RepositoryError")

# ── settings/roles.py: explicit no-op branch ─────────────────────────────────
lit("settings/roles.py", '''    elif role == "launcher":
        pass''', '''    elif role == "launcher":
        pass  # no launcher-specific requirements beyond the checks above''')

# ── sys.path (OD-37) ─────────────────────────────────────────────────────────
lit("guardrails/output_validator.py", '''import sys
from pathlib import Path

# Need to append parent strictly if we load standalone
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from config import JOURNEY_CONFIG''', '''from config import JOURNEY_CONFIG''')
lit("generate_diverse.py", '''import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.absolute()))

from tools.synthetic_data''', '''"""
Optional: generate a large, high-friction demo dataset (about 1M events).

Run from cji_agent/:  python generate_diverse.py
Overwrites data/events.parquet (the default demo data, also read by the golden
snapshot) and, when a database URL is configured outside CJI_ENV=test, replaces
the demo_events table, as `python main.py --mode demo --generate-data` does.
Restore the default data with:  python main.py --mode demo --generate-data
"""
from tools.synthetic_data''')
lit("tools/synthetic_data.py", "# Allow running from project root OR from tools/ directory\nsys.path.insert",
    "# Allow running from project root OR from tools/ directory (until Spec 11 (R-14) packaging)\nsys.path.insert")
lit("tracker/snippet_generator.py", "sys.path.insert(0, str(Path(__file__).resolve().parent.parent))\nfrom config import ROOT",
    "# Script entry (python tracker/snippet_generator.py) until Spec 11 (R-14) packaging.\n"
    "sys.path.insert(0, str(Path(__file__).resolve().parent.parent))\nfrom config import ROOT")
lit("tests/conftest.py", "# Allow running from both cji_agent/ and cji_agent/tests/\nsys.path.insert",
    "# Allow running from both cji_agent/ and cji_agent/tests/ (until Spec 11 (R-14) packaging)\nsys.path.insert")

# ── tools/synthetic_data.py ──────────────────────────────────────────────────
S = "tools/synthetic_data.py"
lit(S, "    fake = Faker()\n    Faker.seed(seed)", "    Faker.seed(seed)")
lit(S, "from sqlalchemy import create_engine\n", "from sqlalchemy import create_engine\nfrom sqlalchemy.exc import SQLAlchemyError\n")
lit(S, '''        except Exception as e:
            logger.error(f"[synthetic_data] Failed to upload to Supabase: {e}")''', '''        except SQLAlchemyError as e:
            logger.error(f"[synthetic_data] Upload to PostgreSQL demo_events failed: {type(e).__name__}", exc_info=True)''')

# ── tools/ingest_json.py (OD-35, CL-10) ──────────────────────────────────────
T = "tools/ingest_json.py"
lit(T, '''Converts real-world event files (JSON / NDJSON / CSV) into the
Parquet format expected by all MCP servers.''', '''Converts real-world event files (JSON / NDJSON / CSV) into rows of the
PostgreSQL table tracking_events (read by the dashboard and by realtime mode).
Default: append, skipping events whose event_id is already stored.
--replace replaces the whole table (Spec 06, OD-35).''')
lit(T, '''  # Append instead of replace
  python tools/ingest_json.py Dataset/hotjar.json --append''', '''  # Replace the whole tracking_events table (the default appends)
  python tools/ingest_json.py Dataset/hotjar.json --replace''')
lit(T, "from typing import Any, Iterator", "from typing import Iterator")
lit(T, '''sys.path.insert(0, str(Path(__file__).parent.parent))
from config import EVENTS_PARQUET, JOURNEY_CONFIG, logger''', '''# Script entry (python tools/ingest_json.py) until Spec 11 (R-14) packaging.
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import EVENTS_PARQUET, JOURNEY_CONFIG, logger''')
lit(T, "from sqlalchemy import create_engine\n", "from sqlalchemy import create_engine, inspect\nfrom sqlalchemy.exc import SQLAlchemyError\n")
lit(T, '''        hes = sess.get("hesitation", {}) or {}
        delay_ms = int(hes.get("first_interaction_delay_ms", 0) or 0)
''', '''        # F-13: hesitation.first_interaction_delay_ms is not mapped to an event yet.
''')
lit(T, '''            except Exception as e:
                logger.error(f"Failed to parse JSON array: {e}")
                return
        if root_key:
            data = data  # root_key not meaningful for arrays
''', '''            except json.JSONDecodeError as e:
                raise ValueError(f"{path}: invalid JSON array: {e}") from e
''')
lit(T, '''    append: bool = False,
) -> tuple[Path, int]:''', '''    append: bool = True,
    replace: bool = False,
) -> tuple[Path, int]:''')
rx(T, r'    """\n    Convert any supported event file .{1,3} events\.parquet\.\n', '''    """
    Convert any supported event file and write it to PostgreSQL tracking_events.

    append (default): add events whose event_id is not stored yet.
    replace=True: replace the whole table (explicit only, Spec 06 OD-35).
    output_path is kept for compatibility; it is not written.
''')
lit(T, '''    col_map     = col_map or {}
    output_path = Path(output_path)''', '''    if append and replace:
        raise ValueError("Choose append or replace, not both.")
    col_map     = col_map or {}
    output_path = Path(output_path)''')
rx(T, r"    engine = create_engine\(db_url\)\n.*?    return output_path, total\n", '''    engine = create_engine(db_url)
    total = _write_tracking_events(df_final, engine, replace=replace)
    logger.info(f"[ingest] Wrote {total:,} rows -> PostgreSQL tracking_events ({'replace' if replace else 'append'})")
    return output_path, total


def _existing_event_ids(engine) -> set[str]:
    """event_ids already stored. A missing table counts as empty; any other failure propagates."""
    if not inspect(engine).has_table("tracking_events"):
        return set()
    ids = pd.read_sql("SELECT event_id FROM tracking_events", engine)
    return set(ids["event_id"].astype(str))


def _write_tracking_events(df: pd.DataFrame, engine, *, replace: bool = False) -> int:
    """Append rows with a new event_id (default), or replace the whole table. Returns rows written."""
    if replace:
        df.to_sql("tracking_events", engine, if_exists="replace", index=False)
        return len(df)
    known = _existing_event_ids(engine)
    new = df[~df["event_id"].astype(str).isin(known)]
    logger.info(f"[ingest] {len(df) - len(new):,} events already stored, {len(new):,} new")
    if not new.empty:
        new.to_sql("tracking_events", engine, if_exists="append", index=False)
    return len(new)
''')
rx(T, r"# Keep old name for backward compatibility\ndef ingest_json\(.*?    return path\n\n\n", "")
rx(T, r'description="Ingest any CJI-compatible event file \(JSON/CSV\) .{1,3} Parquet\.",',
   'description="Ingest any CJI-compatible event file (JSON/CSV) into PostgreSQL tracking_events.",')
lit(T, '''    parser.add_argument("--output",     default=str(EVENTS_PARQUET))''', '''    parser.add_argument("--output",     default=str(EVENTS_PARQUET),
                        help="Kept for compatibility; not written (events go to PostgreSQL tracking_events).")''')
lit(T, '''    parser.add_argument("--append",     action="store_true")''', '''    parser.add_argument("--append",     action="store_true",
                        help="Append new events, skipping stored event_ids (the default; kept for compatibility).")
    parser.add_argument("--replace",    action="store_true",
                        help="Replace the whole tracking_events table with this file.")''')
lit(T, "        out, n = ingest_file(", "        _, n = ingest_file(")
lit(T, r'''            append=args.append,
        )
        mb = out.stat().st_size / 1_048_576
        print(f"\nOK {n:,} events written -> {out}  ({mb:.1f} MB)")''', r'''            append=not args.replace,
            replace=args.replace,
        )
        print(f"\nOK {n:,} events written -> PostgreSQL tracking_events ({'replace' if args.replace else 'append'})")''')
lit(T, r'''    except Exception as exc:
        print(f"\nERR Ingestion failed: {exc}", file=sys.stderr)''', r'''    except (ConfigError, ValueError, OSError, SQLAlchemyError) as exc:
        print(f"\nERR Ingestion failed: {type(exc).__name__}: {exc}", file=sys.stderr)''')

# ── dashboard.py (CL-08, OD-35, OD-37) ───────────────────────────────────────
D = "dashboard.py"
lit(D, "Style: dashboard2.py (Inter font, #F9FAFB, clean white cards)\nData:  DuckDB/Parquet  +  data/last_run.json  (written by main.py)",
    "Style: Inter font, #F9FAFB, clean white cards\nData:  PostgreSQL (DATABASE_URL / SUPABASE_DATABASE_URL)  +  data/last_run.json  (written by main.py)")
lit(D, "dashboard2 style", "card style")
lit(D, '''from sqlalchemy import create_engine

from settings import ConfigError, get_settings, require''', '''from pandas.errors import DatabaseError as PandasDatabaseError
from sqlalchemy import create_engine
from sqlalchemy.exc import ArgumentError, SQLAlchemyError

from repositories.base import RepositoryError, describe_failure
from settings import ConfigError, get_settings, require''')
lit(D, '''try:
    engine = create_engine(DB_URL, pool_pre_ping=True) if DB_URL else None
except Exception:
    engine = None
''', '''try:
    engine = create_engine(DB_URL, pool_pre_ping=True) if DB_URL else None
except (ArgumentError, ImportError) as exc:
    st.error(f"The database URL cannot be used ({type(exc).__name__}). Check DATABASE_URL / SUPABASE_DATABASE_URL.")
    engine = None


class DataLoadError(Exception):
    """A dashboard panel could not read its data (Spec 06, CL-08). The message has no credentials."""

    def __init__(self, panel: str, cause: BaseException):
        detail = RepositoryError(panel, describe_failure(cause)).message
        super().__init__(f"{panel}: {type(cause).__name__}: {detail}")
        self.panel = panel


_LOAD_FAILURES: list[str] = []


def _flush_load_failures() -> None:
    """Show the collected load failures as one warning."""
    if _LOAD_FAILURES:
        st.warning("Could not load: " + "; ".join(dict.fromkeys(_LOAD_FAILURES)))
        _LOAD_FAILURES.clear()


def _load(panel, loader, *args, default=None, flush=False):
    """Call a cached loader. A DataLoadError is recorded for the warning and `default` is returned."""
    try:
        return loader(*args)
    except DataLoadError as exc:
        _LOAD_FAILURES.append(str(exc))
        if flush:
            _flush_load_failures()
        return default
''')
DB_ERRORS = "(SQLAlchemyError, PandasDatabaseError)"
lit(D, '''        try:
            return json.loads(LAST_RUN_FILE.read_text(encoding="utf-8"))
        except Exception:
            return None''', '''        try:
            return json.loads(LAST_RUN_FILE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise DataLoadError("Last run (data/last_run.json)", exc) from exc''')
lit(D, '''            return pd.read_sql(query, conn, params=params)
    except Exception:
        return None''', f'''            return pd.read_sql(query, conn, params=params)
    except {DB_ERRORS} as exc:
        raise DataLoadError("Journey funnel", exc) from exc''')
lit(D, '''    except Exception as e:
        import traceback
        traceback.print_exc()
        return None''', f'''    except {DB_ERRORS} as exc:
        raise DataLoadError("Business KPIs", exc) from exc''')
lit(D, '''        return {"regions": regions_df, "devices": devices_df}
    except Exception:
        return None''', f'''        return {{"regions": regions_df, "devices": devices_df}}
    except {DB_ERRORS} as exc:
        raise DataLoadError("Audience", exc) from exc''')
lit(D, '''        return coords_df
    except Exception:
        return None''', f'''        return coords_df
    except {DB_ERRORS} as exc:
        raise DataLoadError("Heatmap", exc) from exc''')
lit(D, '''        return scores, critical
    except Exception:
        return [], []''', f'''        return scores, critical
    except {DB_ERRORS} as exc:
        raise DataLoadError("Friction scores", exc) from exc''')
lit(D, '''        except Exception as e:
            st.error(f"Error launching pipeline: {e}")''', '''        except OSError as e:
            st.error(f"Error launching pipeline: {type(e).__name__}: {e}")''')
lit(D, '''                except Exception as e:
                    st.error(str(e))''', '''                except (OSError, subprocess.TimeoutExpired) as e:
                    st.error(f"Pipeline could not run: {type(e).__name__}: {e}")''', 2)
rx(D, r'(?m)^(\s*)append_mode = st\.checkbox\(\n\s*"Append to existing data \(don\'t replace\)",\n\s*key="append_mode",\n\s*\)\n',
   lambda m: (
       f'{m[1]}replace_mode = st.checkbox(\n'
       f'{m[1]}    "Replace all rows in tracking_events",\n'
       f'{m[1]}    key="replace_mode",\n'
       f'{m[1]}    help="Off (default): new events are appended; events already stored are skipped. "\n'
       f'{m[1]}         "On: the whole tracking_events table is replaced by this file.",\n'
       f'{m[1]})\n'
       f'{m[1]}if replace_mode:\n'
       f'{m[1]}    st.warning("This deletes every row in tracking_events in the configured database before writing the file.")\n'))
rx(D, r'st\.session_state\["_append_mode"\]\s*=\s*append_mode', 'st.session_state["_replace_mode"] = replace_mode')
lit(D, '''    append_mode  = st.session_state.pop("_append_mode", False)''', '''    replace_mode = st.session_state.pop("_replace_mode", False)''')
lit(D, '''    try:
        # Save the uploaded bytes to a temp file''', '''    tmp_path = None
    try:
        # Save the uploaded bytes to a temp file''')
lit(D, '''        # Call ingest_file directly (same-process, no subprocess needed)
        sys.path.insert(0, str(ROOT))
''', '''        # Call ingest_file directly (same-process, no subprocess needed)
''')
lit(D, '''            append=append_mode,
        )''', '''            append=not replace_mode,
            replace=replace_mode,
        )''')
lit(D, "{row_label} written to database.", "{row_label} written to PostgreSQL tracking_events.")
lit(D, '''    except Exception as exc:
        progress_placeholder.empty()''', '''    except (ConfigError, ValueError, OSError, SQLAlchemyError) as exc:
        progress_placeholder.empty()''')
lit(D, "Ingestion failed: {exc}\")", "Ingestion failed: {DataLoadError('Upload', exc).args[0]}\")")
lit(D, '''        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass''', '''        if tmp_path is not None:
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError as cleanup_exc:
                st.caption(f"Temporary upload file was not removed: {cleanup_exc}")''')
lit(D, '''last          = load_last_run()
journey_df    = load_journey_df(st.session_state.get("sel_property"))
kpis          = load_business_kpis(st.session_state.get("sel_property"))
reports       = load_reports()
audience_data = load_audience_data(st.session_state.get("sel_property"))
heatmap_df    = load_heatmap_data(st.session_state.get("sel_property"))
''', '''_selected     = st.session_state.get("sel_property")
last          = _load("Last run", load_last_run)
journey_df    = _load("Journey funnel", load_journey_df, _selected)
kpis          = _load("Business KPIs", load_business_kpis, _selected)
reports       = load_reports()
audience_data = _load("Audience", load_audience_data, _selected)
heatmap_df    = _load("Heatmap", load_heatmap_data, _selected)
_flush_load_failures()
''')
lit(D, '''friction_list, _ = compute_friction_from_db(st.session_state.get("sel_property"))''',
    '''friction_list, _ = _load("Friction scores", compute_friction_from_db, st.session_state.get("sel_property"), default=([], []), flush=True)''')
lit(D, '''insights_list, _ = compute_insights_from_db(st.session_state.get("sel_property"))''',
    '''insights_list, _ = _load("Insights", compute_insights_from_db, st.session_state.get("sel_property"), default=([], []), flush=True)''')
lit(D, '''        friction_list, critical_steps = compute_friction_from_db(
            st.session_state.get("sel_property")
        )''', '''        friction_list, critical_steps = _load(
            "Friction scores", compute_friction_from_db, st.session_state.get("sel_property"),
            default=([], []), flush=True,
        )''')
lit(D, '''        insights_list, fixes_list = compute_insights_from_db(
            st.session_state.get("sel_property")
        )''', '''        insights_list, fixes_list = _load(
            "Insights", compute_insights_from_db, st.session_state.get("sel_property"),
            default=([], []), flush=True,
        )''')

# ── tests: sys.path copies and unused names ──────────────────────────────────
lit("tests/test_agent_layer.py", '''import sys
import os
import pytest
from pathlib import Path

# Ensure cji_agent is on the path
CJI_ROOT = Path(__file__).parent.parent.resolve()
if str(CJI_ROOT) not in sys.path:
    sys.path.insert(0, str(CJI_ROOT))
''', '''import os
from pathlib import Path

CJI_ROOT = Path(__file__).parent.parent.resolve()   # on sys.path through conftest.py
''')
lit("tests/test_collector_models.py", '''import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).parent.parent))

from collector.models''', '''import pytest
from pydantic import ValidationError

from collector.models''')
lit("tests/test_friction_engine.py", '''import sys
from pathlib import Path

import pytest

# Allow running from both cji_agent/ and cji_agent/tests/
sys.path.insert(0, str(Path(__file__).parent.parent))

from mcp_servers''', '''import pytest

from mcp_servers''')
lit("tests/test_supervisor.py", '''import sys
from pathlib import Path

import pytest

# Allow running from both cji_agent/ and cji_agent/tests/
sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.supervisor import supervisor, route, VALID_WORKERS  # noqa: E402''',
    '''from agents.supervisor import supervisor, route, VALID_WORKERS''')
lit("tests/test_synthetic_data.py", '''import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.synthetic_data''', '''import pandas as pd
import pytest

from tools.synthetic_data''')
lit("tests/test_ingestion_intelligence.py", '''import json
import os
import tempfile
import uuid
from pathlib import Path

import pandas''', '''import tempfile
import uuid

import pandas''')
lit("tests/test_ingestion_intelligence.py", "    first  = detect_schema(csv_path)\n", "    detect_schema(csv_path)          # first call fills the mapping cache\n")

# ── requirements (OD-40) ─────────────────────────────────────────────────────
rx("requirements.txt", r"(?m)^(requests>=2\.32\.0[^\n]*\n)",
   lambda m: m[1] + "tenacity>=8.2,<10          # guardrails/rate_limiter.py (was only a transitive dependency)\n")


def apply(check_only: bool) -> int:
    planned: dict[pathlib.Path, tuple[bytes, str]] = {}
    problems: list[str] = []
    for rel, edits in EDITS.items():
        path = APP / rel
        raw = path.read_bytes()
        text = raw.decode("utf-8")
        crlf = "\r\n" in text
        if crlf and text.count("\r\n") != text.count("\n"):
            problems.append(f"{rel}: mixed line endings")
            continue
        text = text.replace("\r\n", "\n")
        for kind, old, new, count in edits:
            if kind == "lit":
                found = text.count(old)
                if found != count:
                    problems.append(f"{rel}: expected {count}, found {found}: {old[:70]!r}")
                    continue
                text = text.replace(old, new)
            else:
                found = len(re.findall(old, text, flags=re.S))
                if found != count:
                    problems.append(f"{rel}: regex expected {count}, found {found}: {old[:70]!r}")
                    continue
                text = re.sub(old, new, text, flags=re.S)
        planned[path] = (raw, text.replace("\n", "\r\n") if crlf else text)
    if problems:
        print("NOT APPLIED:\n  " + "\n  ".join(problems))
        return 1
    if check_only:
        print(f"check ok: {sum(len(e) for e in EDITS.values())} edits in {len(EDITS)} files")
        return 0
    for path, (_, new_text) in planned.items():
        path.write_bytes(new_text.encode("utf-8"))
    print(f"applied {sum(len(e) for e in EDITS.values())} edits in {len(EDITS)} files")
    return 0


if __name__ == "__main__":
    sys.exit(apply("--check" in sys.argv))
