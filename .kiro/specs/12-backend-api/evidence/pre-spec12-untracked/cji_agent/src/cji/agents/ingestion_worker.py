"""
CJI Ingestion Worker
====================
LangGraph worker node that calls MCP Server 0 (Smart Ingestion Intelligence)
to process any pending raw data files before the Data Worker runs.

Triggered by: Supervisor when state["ingestion_pending_files"] is non-empty.
Skipped by:   Supervisor when no files are pending (standard demo/realtime run).

Follows the same error-isolation pattern as all existing workers:
  P4 — Fail Gracefully, Never Silently
"""

import logging
from datetime import datetime, timezone
from pathlib import Path

from cji.config import INGESTION_CONFIDENCE_THRESHOLD
from cji.integrations.context import run_or_new
from cji.integrations.usage import run_context_arg
from cji.state import CJIState, IngestionResult, WorkerStatus, WorkflowError
from cji.tools.mcp_client import call_tool, mcp_session
from cji.workflow.step import step

log = logging.getLogger("cji.ingestion_worker")

# Logical MCP service name. The endpoint is resolved by tools.mcp_client.SERVER_URLS,
# the same mapping every other worker uses (refactoring.md R-01).
INGESTION_SERVICE = "cji-ingestion-intelligence"


@step("ingestion_worker")
async def ingestion_worker(state: CJIState) -> dict:
    """
    Process pending raw data files through the Smart Ingestion pipeline.

    Flow per file:
      1. detect_schema()      → get mapping config (or use registry cache)
      2. confidence check     → auto-ingest if ≥ threshold, else flag for review
      3. ingest_to_store()    → transform + validate + write
      4. record result        → append to state["ingestion_results"]
    """
    pending_files: list[dict] = state.get("ingestion_pending_files", [])

    if not pending_files:
        return {
            "ingestion_pending_files": [],
            "next_worker":    "data_worker",
            "worker_statuses": [            # appended by the state reducer (Spec 09)
                WorkerStatus(
                    worker="ingestion_worker",
                    status="skipped",
                    message="No pending files — proceeding to Data Worker.",
                )
            ],
        }

    results:        list[IngestionResult] = list(state.get("ingestion_results", []))
    pending_review: list[dict]            = list(state.get("ingestion_pending_review", []))
    errors:         list[WorkflowError]   = []      # new entries only; the state appends them (Spec 09)
    files_processed = 0
    files_flagged   = 0

    for file_info in pending_files:
        file_path   = file_info.get("file_path", "")
        source_hint = file_info.get("source_hint", "")

        if not Path(file_path).exists():
            errors.append({
                "worker": "ingestion_worker",
                "error":  f"File not found: {file_path}",
                "ts":     datetime.now(timezone.utc).isoformat(),
            })
            continue

        try:
            # One MCP session per file: a dropped connection affects only that file.
            async with mcp_session(INGESTION_SERVICE) as session:
                # Step 1 — Schema detection (LLM or cache)
                log.info(f"Detecting schema: {file_path}")
                mapping_config = await call_tool(session, "detect_schema", {
                    "file_path":   file_path,
                    "source_hint": source_hint,
                    "run_context": run_context_arg(run_or_new("ingestion_worker"), state.get("llm_usage")),
                })

                confidence = mapping_config.get("confidence", 0.0)
                log.info(f"  → {mapping_config.get('detected_source')} | confidence: {confidence}")

                # Step 2 — Confidence gate
                if confidence < INGESTION_CONFIDENCE_THRESHOLD:
                    log.warning(f"  → Low confidence ({confidence}) — flagging for human review")
                    pending_review.append({
                        "file_path":      file_path,
                        "mapping_config": mapping_config,
                        "confidence":     confidence,
                        "flagged_at":     datetime.now(timezone.utc).isoformat(),
                    })
                    files_flagged += 1
                    continue

                # Step 3 — Auto-ingest
                log.info(f"  → Auto-ingesting (confidence {confidence} ≥ {INGESTION_CONFIDENCE_THRESHOLD})")
                ingest_result = await call_tool(session, "ingest_to_store", {
                    "file_path":      file_path,
                    "mapping_config": mapping_config,
                    "mode":           state.get("mode", "demo"),
                })

            # Step 4 — Record result
            results.append(IngestionResult(
                ingest_id=       ingest_result.get("ingest_id", ""),
                source_file=     file_path,
                detected_source= mapping_config.get("detected_source", "unknown"),
                confidence=      confidence,
                records_written= ingest_result.get("records_written", 0),
                records_skipped= ingest_result.get("records_skipped", 0),
                destination=     ingest_result.get("destination", ""),
                cached_mapping=  mapping_config.get("cached", False),
                status=          ingest_result.get("status", "error"),
            ))
            files_processed += 1

        except Exception as e:  # broad-except: worker boundary: recorded per file in state errors
            log.error(f"ingestion_worker error for {file_path}: {e}", exc_info=True)
            errors.append({
                "worker": "ingestion_worker",
                "error":  str(e)[:200],
                "ts":     datetime.now(timezone.utc).isoformat(),
            })

    status_msg = (
        f"Processed {files_processed} file(s). "
        f"{files_flagged} flagged for review. "
        f"{len(errors)} error(s)."
    )
    log.info(status_msg)

    # Pending files are always consumed, so a failed or flagged file cannot send
    # the supervisor back to this worker until the iteration cap (Spec 02, R-01).
    return {
        "ingestion_pending_files":  [],
        "ingestion_results":        results,
        "ingestion_pending_review": pending_review,
        "errors":                   errors,
        "next_worker":              "data_worker",
        "worker_statuses": [
            WorkerStatus(
                worker="ingestion_worker",
                status="success" if not errors else "partial",
                message=status_msg,
            )
        ],
    }