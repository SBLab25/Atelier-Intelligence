"""Spec 14 T1/T2 engine edits: settings, provenance state keys and workers (OD-147), ingest_json split (OD-148)."""
from __future__ import annotations

from edit import apply

SRC = "cji_agent/src/cji"

# ── settings (OD-144, OD-148, OD-155) ─────────────────────────────────────────────────────────────────
apply(f"{SRC}/settings/load.py", [
    ('    "CJI_API_CURSOR_SECRET",\n',
     '    "CJI_API_CURSOR_SECRET", "CJI_API_MAX_ACTIVE_RUNS", "CJI_API_MAX_UPLOAD_BYTES", "CJI_API_WRITE_OPERATIONS",\n'),
    ('        cursor_secret=r.secret("CJI_API_CURSOR_SECRET"),\n    )\n',
     '        cursor_secret=r.secret("CJI_API_CURSOR_SECRET"),\n'
     '        max_active_runs=r.integer("CJI_API_MAX_ACTIVE_RUNS", 1, minimum=1, maximum=8),\n'
     '        max_upload_bytes=r.integer("CJI_API_MAX_UPLOAD_BYTES", 10_485_760, minimum=1024, maximum=52_428_800),\n'
     '        write_operations=r.boolean("CJI_API_WRITE_OPERATIONS", True),\n'
     '    )\n'),
])
apply(f"{SRC}/settings/model.py", [
    ('    cursor_secret: SecretStr | None = None   # HMAC key for page cursors; None = random per process\n',
     '    cursor_secret: SecretStr | None = None   # HMAC key for page cursors; None = random per process\n'
     '    max_active_runs: int = 1            # runs started or resumed by one API process at once (Spec 14)\n'
     '    max_upload_bytes: int = 10_485_760  # ingestion validation upload limit (Spec 14)\n'
     '    write_operations: bool = True       # false: start/resume/ingestion operations are not mounted (Spec 14)\n'),
])

# ── state keys (OD-147) ───────────────────────────────────────────────────────────────────────────────
apply(f"{SRC}/state.py", [
    ('      - insight_worker, report_worker: llm_usage (Spec 08)\n',
     '      - insight_worker, report_worker: llm_usage (Spec 08)\n'
     '      - insight_worker: insight_provenance; report_worker: narrative_provenance (Spec 14)\n'),
    ('    llm_usage: dict     # {calls, input_tokens, output_tokens, cost_usd} for this run\'s budget\n',
     '    llm_usage: dict     # {calls, input_tokens, output_tokens, cost_usd} for this run\'s budget\n\n'
     '    # ── PROVENANCE (Spec 14, OD-147): {source, model, provider, reason, generated_at} ──\n'
     '    insight_provenance:   dict   # insight_id -> provenance of that insight\n'
     '    narrative_provenance: dict   # provenance of the narrative\n'),
])
apply(f"{SRC}/workflow/runtime.py", [
    ('"report_path": "", "narrative": "", "llm_usage": {},\n',
     '"report_path": "", "narrative": "", "llm_usage": {},\n'
     '        "insight_provenance": {}, "narrative_provenance": {},\n'),
])

# ── workers: record the gateway metadata the workers already receive (F-73) ──────────────────────────
apply(f"{SRC}/agents/workers.py", [
    ('from cji.workflow.step import step\n',
     'from cji.workflow.step import step, utc_now\n'),
    ('def _unwrap_narrative(',
     'def _provenance(info: dict[str, Any] | None, generated_at: str = "") -> dict[str, Any]:\n'
     '    """Where an LLM-backed result came from (Spec 14, OD-147), from the gateway metadata of its call.\n'
     '    The model and provider are kept only when the model wrote the result (as for narrative_model, Spec 10)."""\n'
     '    outcome = (info or {}).get("outcome") if isinstance(info, dict) else None\n'
     '    source = {"ok": "llm", "fallback": "fallback"}.get(str(outcome), "not_recorded")\n'
     '    llm = source == "llm" and isinstance(info, dict)\n'
     '    return {\n'
     '        "source": source,\n'
     '        "model": (str(info.get("model") or "") or None) if llm and info else None,\n'
     '        "provider": (str(info.get("provider") or "") or None) if llm and info else None,\n'
     '        "reason": (str(info.get("code") or "") or None) if source == "fallback" and info else None,\n'
     '        "generated_at": generated_at or utc_now(),\n'
     '    }\n\n\n'
     'def _unwrap_narrative('),
    ('@step("insight_worker", describe=_error_text, fallback=lambda: {"insights": [], "prioritized_fixes": []})',
     '@step("insight_worker", describe=_error_text,\n'
     '      fallback=lambda: {"insights": [], "prioritized_fixes": [], "insight_provenance": {}})'),
    ('            "insights":          [],\n            "prioritized_fixes": [],\n            "next_worker":       "supervisor",\n',
     '            "insights":          [],\n            "prioritized_fixes": [],\n            "insight_provenance": {},\n'
     '            "next_worker":       "supervisor",\n'),
    ('        insights = []\n\n        # 1. Generate insight per critical step\n',
     '        insights = []\n        provenance: dict[str, dict[str, Any]] = {}\n\n'
     '        # 1. Generate insight per critical step\n'),
    ('            insight["run_id"] = run_id\n            insights.append(insight)\n',
     '            insight["run_id"] = run_id\n            insights.append(insight)\n'
     '            provenance[insight["insight_id"]] = _provenance(info)      # Spec 14, OD-147\n'),
    ('        "prioritized_fixes": ranked_fixes,\n        "llm_usage":         usage,\n',
     '        "prioritized_fixes": ranked_fixes,\n        "insight_provenance": provenance,\n'
     '        "llm_usage":         usage,\n'),
    ('@step("report_worker", describe=_error_text, fallback=lambda: {"report_path": "", "narrative": ""})',
     '@step("report_worker", describe=_error_text,\n'
     '      fallback=lambda: {"report_path": "", "narrative": "", "narrative_provenance": {}})'),
    ('        narrative_source = {"ok": "llm", "fallback": "fallback"}.get(str(outcome), "unknown")\n',
     '        narrative_source = {"ok": "llm", "fallback": "fallback"}.get(str(outcome), "unknown")\n'
     '        narrative_provenance = _provenance(info, str(narrative_result.get("generated_at") or ""))\n'),
    ('        "narrative":   narrative,\n        "llm_usage":   usage,\n',
     '        "narrative":   narrative,\n        "narrative_provenance": narrative_provenance,\n'
     '        "llm_usage":   usage,\n'),
])

# ── ingest_json: parse_file / write_rows split, same ingest_file behaviour (OD-148, F-75) ────────────
detections = ["CSV", "JSON array", "NDJSON", "all_sources_bundle", "GA4 clickstream", "Hotjar sessions",
              "UXCam sessions", "Hotjar-style sessions (fallback)", "Surveys", "Support tickets", "NDJSON (fallback)"]
ing = [(f'logger.info("[ingest] Detected: {name}")', f'_note(detected, "{name}")', 1) for name in detections]
ing[2] = ('logger.info("[ingest] Detected: NDJSON")', '_note(detected, "NDJSON")', 1)
apply(f"{SRC}/tools/ingest_json.py", [
    ('import uuid\nfrom datetime import datetime, timezone\n',
     'import uuid\nfrom dataclasses import dataclass\nfrom datetime import datetime, timezone\n'),
    ('def _detect_and_yield(path: Path, col_map: dict[str, str],\n                      root_key: str | None) -> Iterator[dict]:\n',
     'def _note(detected: list[str] | None, name: str) -> None:\n'
     '    """Log the detected format and record it for parse_file (Spec 14)."""\n'
     '    logger.info(f"[ingest] Detected: {name}")\n'
     '    if detected is not None:\n'
     '        detected.append(name)\n\n\n'
     'def _detect_and_yield(path: Path, col_map: dict[str, str],\n'
     '                      root_key: str | None, detected: list[str] | None = None) -> Iterator[dict]:\n'),
    *ing,
    ('            logger.info(f"[ingest] Using root_key=\'{root_key}\'")\n',
     '            logger.info(f"[ingest] Using root_key=\'{root_key}\'")\n'
     '            if detected is not None:\n                detected.append("JSON object (root key)")\n'),
    ('                logger.info(f"[ingest] Auto-found list under key \'{k}\' (len={len(v)})")\n',
     '                logger.info(f"[ingest] Auto-found list under key \'{k}\' (len={len(v)})")\n'
     '                if detected is not None:\n                    detected.append("JSON object (list value)")\n'),
    ('        logger.info("[ingest] Single JSON object → treating as one record")\n',
     '        logger.info("[ingest] Single JSON object → treating as one record")\n'
     '        if detected is not None:\n            detected.append("single JSON object")\n'),
    ('def _finalise(df: pd.DataFrame) -> pd.DataFrame:\n    """Ensure correct dtypes and all required columns."""\n',
     'def _finalise(df: pd.DataFrame, stats: ParseStats | None = None) -> pd.DataFrame:\n'
     '    """Ensure correct dtypes and all required columns. `stats` (Spec 14) counts dropped and repaired rows."""\n'),
    ('    if unknown_type.any():\n',
     '    if stats is not None:\n        stats.dropped_event_type += int(unknown_type.sum())\n    if unknown_type.any():\n'),
    ('    bad_ts = df["timestamp"].isna().sum()\n',
     '    bad_ts = df["timestamp"].isna().sum()\n'
     '    if stats is not None:\n        stats.repaired_timestamp += int(bad_ts)\n'),
    ('# ═══════════════════════════════════════════════════════════════════════════════\n# Public API\n'
     '# ═══════════════════════════════════════════════════════════════════════════════\n\ndef ingest_file(',
     '# ═══════════════════════════════════════════════════════════════════════════════\n# Public API\n'
     '# ═══════════════════════════════════════════════════════════════════════════════\n\n'
     '@dataclass\n'
     'class ParseStats:\n'
     '    """What parse_file found (Spec 14, OD-148): the validation feedback before anything is written."""\n'
     '    format: str = "unknown"\n'
     '    parsed: int = 0                 # rows extracted from the file\n'
     '    accepted: int = 0               # rows kept after normalisation\n'
     '    dropped_event_type: int = 0     # rows skipped: event type outside the CJI taxonomy\n'
     '    repaired_timestamp: int = 0     # rows whose unparseable timestamp was replaced by now()\n\n\n'
     'def parse_file(\n'
     '    input_path: Path,\n'
     '    col_map: dict[str, str] | None = None,\n'
     '    root_key: str | None = None,\n'
     '    chunk_size: int = 100_000,\n'
     ') -> tuple[pd.DataFrame, ParseStats]:\n'
     '    """Parse and normalise an event file without writing it. ValueError when no records can be extracted."""\n'
     '    col_map = col_map or {}\n'
     '    stats = ParseStats()\n'
     '    detected: list[str] = []\n'
     '    rows:   list[dict] = []\n'
     '    chunks: list[pd.DataFrame] = []\n'
     '    total  = 0\n\n'
     '    for row in _detect_and_yield(input_path, col_map, root_key, detected):\n'
     '        rows.append(row)\n'
     '        stats.parsed += 1\n'
     '        if len(rows) >= chunk_size:\n'
     '            df_c = _finalise(pd.DataFrame(rows), stats)\n'
     '            chunks.append(df_c)\n'
     '            total += len(df_c)\n'
     '            logger.info(f"  processed {total:,} rows so far...")\n'
     '            rows = []\n\n'
     '    if rows:\n'
     '        df_c = _finalise(pd.DataFrame(rows), stats)\n'
     '        chunks.append(df_c)\n'
     '        total += len(df_c)\n\n'
     '    stats.format = detected[0] if detected else "unknown"\n'
     '    if not chunks:\n'
     '        raise ValueError(\n'
     '            "No records could be extracted from the file.\\n"\n'
     '            "Check that the file is valid JSON/CSV and contains records.\\n"\n'
     '            f"Inspected: {input_path}"\n'
     '        )\n'
     '    df_final = pd.concat(chunks, ignore_index=True)\n'
     '    stats.accepted = len(df_final)\n'
     '    return df_final, stats\n\n\n'
     'def write_rows(df: pd.DataFrame, *, replace: bool = False, engine=None) -> int:\n'
     '    """Write parsed rows to PostgreSQL tracking_events (append skips stored event_ids). Returns rows written.\n'
     '    `engine` defaults to the configured database (ConfigError without one)."""\n'
     '    if engine is None:\n'
     '        db_url = get_settings().database.url_value()\n'
     '        if not db_url:\n'
     '            raise ConfigError([database_missing("Writing ingested events to tracking_events")])\n'
     '        engine = create_engine(db_url)\n'
     '    return _write_tracking_events(df, engine, replace=replace)\n\n\n'
     'def ingest_file('),
    ('    rows:   list[dict] = []\n    chunks: list[pd.DataFrame] = []\n    total  = 0\n\n'
     '    for row in _detect_and_yield(input_path, col_map, root_key):\n'
     '        rows.append(row)\n'
     '        if len(rows) >= chunk_size:\n'
     '            df_c = _finalise(pd.DataFrame(rows))\n'
     '            chunks.append(df_c)\n'
     '            total += len(df_c)\n'
     '            logger.info(f"  processed {total:,} rows so far...")\n'
     '            rows = []\n\n'
     '    if rows:\n'
     '        df_c = _finalise(pd.DataFrame(rows))\n'
     '        chunks.append(df_c)\n'
     '        total += len(df_c)\n\n'
     '    if not chunks:\n'
     '        raise ValueError(\n'
     '            "No records could be extracted from the file.\\n"\n'
     '            "Check that the file is valid JSON/CSV and contains records.\\n"\n'
     '            f"Inspected: {input_path}"\n'
     '        )\n\n'
     '    df_final = pd.concat(chunks, ignore_index=True)\n\n'
     '    db_url = get_settings().database.url_value()\n'
     '    if not db_url:\n'
     '        raise ConfigError([database_missing("Writing ingested events to tracking_events")])\n'
     '    engine = create_engine(db_url)\n'
     '    total = _write_tracking_events(df_final, engine, replace=replace)\n',
     '    df_final, _stats = parse_file(input_path, col_map, root_key, chunk_size)      # Spec 14 split\n'
     '    total = write_rows(df_final, replace=replace)\n'),
])
