"""
CJI MCP Server 0 — Smart Ingestion Intelligence
================================================
Accepts any raw data format, uses an LLM to map incoming fields to the
canonical CJI schema, validates the transformation, and writes clean
records to the appropriate store (DuckDB demo or Supabase realtime).

Design Principles Applied:
  P9  — Schema Intelligence Over Schema Enforcement
  P10 — LLM Called Once Per Source Type (mapping registry cache)
  P11 — Confidence-Gated Auto-Ingestion (threshold: 0.80)
  P12 — ChromaDB for Semantic Field Pre-Matching
  P13 — Output always normalised to canonical CJI schema

Transport: HTTP/SSE (not STDIO — avoids the DuckDB STDIO deadlock
           documented in docs/development_status.md)
"""

import hashlib
import json
from collections import Counter
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import get_args

import pandas as pd
from fastmcp import FastMCP
from pydantic import BaseModel, ValidationError, field_validator

from cji.config import (
    INGESTION_CONFIDENCE_THRESHOLD,
    INGESTION_MAPPING_REGISTRY,
    INGESTION_SAMPLE_ROWS,
)
from cji.domain.events import ALLOWED_EVENT_TYPES, EVENT_RECORD, EventType, sanitise_url
from cji.integrations import GatewayError, LLMGateway, LLMRequest, RunContext, new_correlation_id
from cji.repositories import RepositoryError, get_repository
from cji.settings import ConfigError

# ── Server setup ───────────────────────────────────────────────────────────────
mcp = FastMCP("cji-ingestion-intelligence")
log = logging.getLogger("cji.ingestion")

# ── Canonical schema (passed to LLM as system prompt context) ──────────────────
CANONICAL_SCHEMA = {
    "canonical_fields": {
        "event_id":    {"type": "string",   "required": True,  "description": "Unique UUID for this event. Generate if missing."},
        "user_id":     {"type": "string",   "required": True,  "description": "Anonymous user identifier — UUID, never PII."},
        "session_id":  {"type": "string",   "required": True,  "description": "Browser session identifier — UUID per tab/session."},
        "journey_id":  {"type": "string",   "required": True,  "description": "Journey name e.g. onboarding, checkout, login."},
        "step_id":     {"type": "string",   "required": True,  "description": "Step within the journey e.g. email_verification, payment_info."},
        "event_type":  {"type": "string",   "required": True,  "description": "One of: page_view, click, form_submit, error, rage_click, abandon, step_complete, identify."},
        "timestamp":   {"type": "datetime", "required": True,  "description": "ISO-8601 UTC datetime e.g. 2026-04-22T14:32:00Z."},
        "duration_ms": {"type": "integer",  "required": False, "description": "Time on step in milliseconds. 0 for instant events."},
        "url":         {"type": "string",   "required": False, "description": "Page URL — sanitised, no query params, no PII."},
        "metadata":    {"type": "string",   "required": False, "description": "JSON string with extra event-specific payload."},
    },
    # Taxonomy from domain/events.py, in declaration order (Spec 03, RC-04).
    "allowed_event_types": list(get_args(EventType)),
    "pii_rules": [
        "Strip all query parameters from URL fields",
        "Replace email addresses with [REDACTED]",
        "user_id must be an anonymous UUID — never a real name or email",
    ],
}

# ALLOWED_EVENT_TYPES is re-exported from domain.events (single definition).

# ── File-ingestion adapter (Spec 03, design §4) ───────────────────────────────
# Third-party files use their own event names, so this adapter coerces unknown
# event types to "page_view" (documented behaviour) instead of rejecting them.
# apply_mapping() counts every coercion (records_coerced) and checks each output
# record against domain.events.EventRecord. Replaced by repositories in Spec 05.
class CanonicalEvent(BaseModel):
    event_id:    str
    user_id:     str
    session_id:  str
    journey_id:  str
    step_id:     str
    event_type:  str
    timestamp:   str
    duration_ms: int  = 0
    url:         str  = ""
    metadata:    str  = "{}"

    @field_validator("event_type")
    @classmethod
    def validate_event_type(cls, v: str) -> str:
        if v not in ALLOWED_EVENT_TYPES:
            # Coerce to closest valid type rather than rejecting
            return "page_view"
        return v

    @field_validator("metadata")
    @classmethod
    def validate_metadata(cls, v: str) -> str:
        try:
            json.loads(v)
        except (json.JSONDecodeError, TypeError):
            return "{}"
        return v


# ── Mapping registry (persistent JSON file) ───────────────────────────────────
def _load_registry() -> dict:
    if INGESTION_MAPPING_REGISTRY.exists():
        return json.loads(INGESTION_MAPPING_REGISTRY.read_text())
    return {}


def _save_registry(registry: dict) -> None:
    INGESTION_MAPPING_REGISTRY.parent.mkdir(parents=True, exist_ok=True)
    INGESTION_MAPPING_REGISTRY.write_text(json.dumps(registry, indent=2))


def _column_fingerprint(columns: list[str]) -> str:
    """SHA-256 of sorted lowercase column names — used as registry cache key."""
    key = "|".join(sorted(c.lower().strip() for c in columns))
    return hashlib.sha256(key.encode()).hexdigest()[:16]


# ── File loader ────────────────────────────────────────────────────────────────
def _load_file(file_path: str) -> pd.DataFrame:
    """Load any supported file format into a DataFrame."""
    path = Path(file_path)
    ext  = path.suffix.lower()
    loaders = {
        ".csv":     lambda p: pd.read_csv(p),
        ".json":    lambda p: pd.read_json(p),
        ".jsonl":   lambda p: pd.read_json(p, lines=True),
        ".xlsx":    lambda p: pd.read_excel(p, engine="openpyxl"),
        ".xls":     lambda p: pd.read_excel(p),
        ".parquet": lambda p: pd.read_parquet(p),
    }
    if ext not in loaders:
        raise ValueError(f"Unsupported file format: {ext}. Supported: {list(loaders.keys())}")
    return loaders[ext](path)


# ── PII sanitisation (consistent with existing guardrails) ───────────────────
def _sanitise_url(url: str) -> str:
    """Strip query params and fragments from URL (domain.events.sanitise_url)."""
    if not url:
        return ""
    return sanitise_url(str(url))


def _sanitise_user_id(user_id: str) -> str:
    """Ensure user_id looks like a UUID — if it contains @ it's an email, anonymise it."""
    uid = str(user_id)
    if "@" in uid or len(uid) > 50:
        return str(uuid.uuid5(uuid.NAMESPACE_DNS, uid))
    return uid


# ── LLM caller (Spec 08: through the gateway; one provider, no silent fallback) ─
_llm: LLMGateway | None = None


def llm_gateway() -> LLMGateway:
    global _llm
    if _llm is None:
        _llm = LLMGateway.from_settings("cji-ingestion-intelligence")
    return _llm


async def _call_llm_for_mapping(sample_json: str, columns: list[str], source_hint: str = "",
                                purpose: str = "schema_mapping", ctx: RunContext | None = None) -> dict:
    """
    Call the configured LLM to generate a field mapping config.
    Returns parsed JSON dict. Raises RuntimeError (with the gateway error code only) if the call fails.
    """
    system_prompt = f"""You are a data schema analyst for a BFSI customer journey analytics platform.
Your task: map an incoming dataset's columns to the CJI canonical event schema.

CANONICAL SCHEMA (your target):
{json.dumps(CANONICAL_SCHEMA, indent=2)}

RULES:
1. Return ONLY valid JSON. No explanation, no preamble, no markdown fences.
2. field_mapping: maps incoming column name → canonical field name.
3. derived_fields: for canonical fields not directly present, describe the derivation rule in plain English.
4. missing_fields: list canonical fields that cannot be mapped or derived at all.
5. confidence: float 0.0–1.0. Use 0.9+ only when mapping is unambiguous.
6. transformation_notes: list any data type conversions needed (e.g. "timestamp is Unix microseconds — divide by 1e6").
7. warnings: flag anything suspicious but non-blocking.
{f'Source hint from user: "{source_hint}"' if source_hint else ""}"""

    user_prompt = f"""Incoming data sample ({INGESTION_SAMPLE_ROWS} rows):
{sample_json}

Column names detected: {json.dumps(columns)}

Generate the mapping config JSON now."""

    request = LLMRequest(purpose=purpose, system=system_prompt, user=user_prompt, response_format="json",
                         max_tokens=1500)
    try:
        run = ctx or RunContext(correlation_id=new_correlation_id(), worker="ingestion")
        result = await llm_gateway().complete(request, run)
    except GatewayError as exc:
        raise RuntimeError(f"LLM mapping failed: {exc}") from exc
    return dict(result.data or {})


def _unmapped_config(fingerprint: str, code: str) -> dict:
    """Result when the LLM produced no mapping: confidence 0.0 sends the file to human review (as before)."""
    return {
        "detected_source":      None,
        "source_id":            "unknown",
        "confidence":           0.0,
        "field_mapping":        {},
        "derived_fields":       {},
        "missing_fields":       [],
        "transformation_notes": [],
        "warnings":             [f"LLM schema mapping unavailable ({code}); map this file manually."],
        "llm_error":            code,
        "column_fingerprint":   fingerprint,
        "llm_model_used":       llm_gateway().model,
        "cached":               False,
    }


# ── MCP Tools ──────────────────────────────────────────────────────────────────

@mcp.tool()
async def detect_schema(file_path: str, source_hint: str = "", run_context: dict | None = None) -> dict:
    """
    Analyse a raw data file and generate a field mapping config to the
    canonical CJI schema. Checks the mapping registry cache first.

    Args:
        file_path:   Absolute path to the raw data file.
        source_hint: Optional human hint e.g. 'GA4 export', 'Hotjar recording'.
        run_context: Correlation id and remaining LLM budget from the workflow (Spec 08).

    Returns:
        Mapping config dict with detected_source, confidence, field_mapping,
        derived_fields, missing_fields, transformation_notes, cached flag.
    """
    log.info(f"detect_schema called: {file_path} (hint: '{source_hint}')")

    df      = _load_file(file_path)
    columns = df.columns.tolist()
    fp      = _column_fingerprint(columns)

    # ── Cache check ─────────────────────────────────────────────────────────
    registry = _load_registry()
    if fp in registry:
        log.info(f"Cache hit for fingerprint {fp} — skipping LLM call")
        cached = registry[fp].copy()
        cached["cached"] = True
        cached["last_used"] = datetime.now(timezone.utc).isoformat()
        cached["use_count"] = cached.get("use_count", 0) + 1
        registry[fp] = cached
        _save_registry(registry)
        return cached

    # ── Sample & call LLM ────────────────────────────────────────────────────
    sample_df   = df.head(INGESTION_SAMPLE_ROWS)
    sample_json = sample_df.fillna("").astype(str).to_json(orient="records", indent=2)

    ctx = RunContext.from_arg(run_context, new_correlation_id())
    try:
        mapping = await _call_llm_for_mapping(sample_json, columns, source_hint, ctx=ctx)
    except RuntimeError as exc:
        # Kept from Spec 07: a file the LLM cannot map goes to human review, not to workflow errors.
        code = getattr(exc.__cause__, "code", None) or "llm_failed"
        log.warning("Schema mapping unavailable (%s); flagging the file for manual review", code)
        return _unmapped_config(fp, code)

    # Attach metadata
    source_id = (
        mapping.get("detected_source", "unknown")
        .lower().replace(" ", "_").replace("/", "_")[:40]
    )
    mapping["source_id"]           = source_id
    mapping["column_fingerprint"]  = fp
    mapping["llm_model_used"]      = llm_gateway().model
    mapping["cached"]              = False
    mapping["created_at"]          = datetime.now(timezone.utc).isoformat()
    mapping["last_used"]           = mapping["created_at"]
    mapping["use_count"]           = 1

    log.info(f"Schema detected: {mapping.get('detected_source')} | confidence: {mapping.get('confidence')}")
    return mapping


def _derived_event_ids(df: pd.DataFrame) -> list[str]:
    """uuid5 of each row's canonical JSON plus its occurrence number (identical rows stay distinct)."""
    seen: Counter[str] = Counter()
    ids = []
    for row in df.to_dict(orient="records"):
        key = json.dumps(row, sort_keys=True, default=str)
        ids.append(str(uuid.uuid5(uuid.NAMESPACE_URL, f"cji-event:{key}#{seen[key]}")))
        seen[key] += 1
    return ids


@mcp.tool()
def apply_mapping(file_path: str, mapping_config: dict) -> dict:
    """
    Apply a mapping config to a full raw data file, transforming it into
    canonical CJI records. Returns transformation stats and a sample.

    Args:
        file_path:      Absolute path to the raw data file.
        mapping_config: Output from detect_schema() or a registry entry.

    Returns:
        Dict with records_total, records_passed, records_failed, sample_output,
        failure_reasons, ready_to_ingest flag.
    """
    log.info(f"apply_mapping called: {file_path}")

    df            = _load_file(file_path)
    field_mapping = mapping_config.get("field_mapping", {})
    notes         = mapping_config.get("transformation_notes", [])

    # ── Rename mapped columns ─────────────────────────────────────────────────
    rename_map = {src: tgt for src, tgt in field_mapping.items() if src in df.columns}
    df = df.rename(columns=rename_map)

    # ── Apply derivation rules ────────────────────────────────────────────────
    # journey_id
    if "journey_id" not in df.columns:
        df["journey_id"] = "imported_journey"   # F-13: derived_fields["journey_id"] is not applied

    # step_id — derive from url if not present
    if "step_id" not in df.columns and "url" in df.columns:
        df["step_id"] = df["url"].astype(str).str.split("/").str[-1].str.replace("-", "_").str.replace(".", "_")
    elif "step_id" not in df.columns:
        df["step_id"] = "unknown_step"

    # Spec 09 (OD-73): derived from the row, so loading the same file again stores nothing twice
    # (the repositories dedupe by event_id)
    if "event_id" not in df.columns:
        df["event_id"] = _derived_event_ids(df)

    # session_id — generate per unique user if missing
    if "session_id" not in df.columns and "user_id" in df.columns:
        df["session_id"] = df["user_id"].astype(str).apply(
            lambda u: str(uuid.uuid5(uuid.NAMESPACE_DNS, u + "_session"))
        )
    elif "session_id" not in df.columns:
        df["session_id"] = [str(uuid.uuid4()) for _ in range(len(df))]

    # event_type — coerce unrecognised values (documented adapter behaviour), counted
    records_coerced = 0
    if "event_type" in df.columns:
        raw_types = df["event_type"].astype(str)
        unknown = ~raw_types.isin(ALLOWED_EVENT_TYPES)
        records_coerced = int(unknown.sum())
        df["event_type"] = raw_types.where(~unknown, "page_view")
    else:
        df["event_type"] = "page_view"

    # timestamp — attempt multiple format conversions based on notes
    if "timestamp" in df.columns:
        for note in notes:
            note_l = note.lower()
            if "microsecond" in note_l or "microsec" in note_l:
                df["timestamp"] = pd.to_numeric(df["timestamp"], errors="coerce") / 1_000_000
                df["timestamp"] = pd.to_datetime(df["timestamp"], unit="s", utc=True).astype(str)
                break
            elif "millisecond" in note_l or "ms" in note_l:
                df["timestamp"] = pd.to_numeric(df["timestamp"], errors="coerce") / 1_000
                df["timestamp"] = pd.to_datetime(df["timestamp"], unit="s", utc=True).astype(str)
                break
        else:
            df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce").astype(str)
    else:
        df["timestamp"] = datetime.now(timezone.utc).isoformat()

    # duration_ms — ensure integer
    if "duration_ms" in df.columns:
        df["duration_ms"] = pd.to_numeric(df["duration_ms"], errors="coerce").fillna(0).astype(int)
    else:
        df["duration_ms"] = 0

    # url — sanitise
    if "url" in df.columns:
        df["url"] = df["url"].astype(str).apply(_sanitise_url)
    else:
        df["url"] = ""

    # user_id — anonymise if needed
    if "user_id" in df.columns:
        df["user_id"] = df["user_id"].astype(str).apply(_sanitise_user_id)

    # metadata — pack remaining unmapped columns into JSON
    canonical_cols = set(CANONICAL_SCHEMA["canonical_fields"].keys())
    extra_cols     = [c for c in df.columns if c not in canonical_cols]
    if extra_cols:
        df["metadata"] = df[extra_cols].fillna("").astype(str).apply(
            lambda row: json.dumps(row.to_dict()), axis=1
        )
    elif "metadata" not in df.columns:
        df["metadata"] = "{}"

    # ── Validate with Pydantic v2 ─────────────────────────────────────────────
    records_passed  = []
    records_failed  = []
    failure_reasons = []

    for _, row in df.iterrows():
        try:
            evt = CanonicalEvent(**{k: row.get(k, "") for k in CANONICAL_SCHEMA["canonical_fields"]})
            record = evt.model_dump()
            EVENT_RECORD.validate_python(record)   # adapter output must be a stored EventRecord
            records_passed.append(record)
        except (ValidationError, ValueError, TypeError) as e:
            records_failed.append(row.to_dict())
            failure_reasons.append(str(e)[:120])

    log.info(f"apply_mapping: {len(records_passed)} passed, {len(records_failed)} failed, "
             f"{records_coerced} event types coerced to page_view")

    return {
        "records_total":    len(df),
        "records_passed":   len(records_passed),
        "records_failed":   len(records_failed),
        "records_coerced":  records_coerced,
        "failure_reasons":  list(set(failure_reasons))[:10],
        "sample_output":    records_passed[:5],
        "ready_to_ingest":  len(records_passed) > 0,
        "_records_internal": records_passed,   # used by ingest_to_store
    }


@mcp.tool()
async def validate_transformed_data(records_sample: list) -> dict:
    """
    Run a secondary quality check on transformed records.
    Uses Pydantic v2 structural validation + lightweight LLM review.

    Args:
        records_sample: List of up to 50 canonical CJI records (dicts).

    Returns:
        Dict with quality_score, pydantic_errors, llm_quality_verdict,
        anomalies, approved_for_ingest flag.
    """
    log.info(f"validate_transformed_data: checking {len(records_sample)} records")

    sample    = records_sample[:50]
    errors    = []
    anomalies = []

    for rec in sample:
        try:
            CanonicalEvent(**rec)
        except ValidationError as e:
            errors.append(str(e)[:120])

    # Anomaly checks
    durations = [r.get("duration_ms", 0) for r in sample]
    if any(d > 600_000 for d in durations):
        anomalies.append(f"{sum(d > 600_000 for d in durations)} records have duration_ms > 600s — possible outliers")

    journey_ids = set(r.get("journey_id", "") for r in sample)
    if len(journey_ids) == 1 and "imported_journey" in journey_ids:
        anomalies.append("All records have journey_id='imported_journey' — consider setting a meaningful journey name")

    quality_score = max(0.0, 1.0 - (len(errors) / max(len(sample), 1)))

    # Lightweight LLM verdict (optional — skip if no API key)
    llm_verdict = "LLM quality check skipped — no LLM provider configured."
    if llm_gateway().available:
        try:
            # F-12: the quality check reuses the schema-mapping prompt (unchanged by Spec 08).
            result = await _call_llm_for_mapping(
                json.dumps(sample[:5], indent=2),
                list(sample[0].keys()) if sample else [],
                source_hint="quality check — not schema mapping",
                purpose="quality_check",
            )
            llm_verdict = str(result)
        except (RuntimeError, ValueError, OSError):
            llm_verdict = "LLM quality check unavailable — proceeding with Pydantic validation only."

    return {
        "quality_score":        round(quality_score, 3),
        "pydantic_errors":      errors[:10],
        "llm_quality_verdict":  llm_verdict,
        "anomalies":            anomalies,
        "approved_for_ingest":  quality_score >= 0.85 and len(errors) < 5,
    }


@mcp.tool()
def ingest_to_store(file_path: str, mapping_config: dict, mode: str = "") -> dict:
    """
    Full pipeline: detect → apply → validate → write to DuckDB or Supabase.
    Auto-saves the mapping to registry if confidence >= INGESTION_CONFIDENCE_THRESHOLD.

    Args:
        file_path:      Absolute path to raw data file.
        mapping_config: Output from detect_schema().
        mode:           'demo' or 'realtime'. Defaults to CJI_MODE from config.

    Returns:
        Dict with status, records_written, records_skipped, destination, duration_ms.
    """
    start_ms = datetime.now().timestamp() * 1000
    # The store is chosen once from the server's settings (Spec 05); a request for the
    # other mode is refused instead of writing to the wrong store (OD-33).
    try:
        repo = get_repository()
    except ConfigError as exc:
        return {"status": "error", "error": "; ".join(exc.problems), "records_written": 0, "records_skipped": 0}
    if mode in ("demo", "realtime") and mode != repo.mode:
        return {
            "status":          "error",
            "error":           (f"this server is configured for {repo.mode} mode but the request asked for "
                                f"{mode}. Start the MCP servers with --mode {mode}, or run the analysis in "
                                f"{repo.mode} mode."),
            "records_written": 0,
            "records_skipped": 0,
        }
    log.info(f"ingest_to_store: mode={repo.mode}, file={file_path}")

    # Apply mapping
    transform_result = apply_mapping(file_path, mapping_config)
    if not transform_result["ready_to_ingest"]:
        return {
            "status":          "error",
            "error":           "Transformation produced zero valid records — check mapping config.",
            "records_written": 0,
            "records_skipped": transform_result["records_failed"],
        }

    records = transform_result["_records_internal"]

    # Write through the repository: one all-or-nothing batch, idempotent by event_id
    # (demo: atomic Parquet replace; realtime: tracking_events in one transaction).
    try:
        written = repo.append_events(records)
    except RepositoryError as exc:
        log.error(f"ingest_to_store failed, nothing written: {exc.message}")
        return {
            "status":          "error",
            "error":           exc.message,
            "records_written": 0,
            "records_skipped": transform_result["records_failed"],
            "records_coerced": transform_result["records_coerced"],
        }
    destination = written.destination

    # Auto-save mapping to registry
    confidence = mapping_config.get("confidence", 0.0)
    if confidence >= INGESTION_CONFIDENCE_THRESHOLD:
        save_mapping(mapping_config.get("source_id", "unknown"), mapping_config)

    duration = int(datetime.now().timestamp() * 1000 - start_ms)
    ingest_id = f"ingest_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"

    log.info(f"ingest_to_store complete: {written.written} written, {written.duplicates} already stored "
             f"→ {destination} in {duration}ms")

    return {
        "status":          "success",
        "records_written": written.written,
        "records_duplicate": written.duplicates,
        "records_skipped": transform_result["records_failed"],
        "records_coerced": transform_result["records_coerced"],
        "destination":     destination,
        "duration_ms":     duration,
        "ingest_id":       ingest_id,
    }


@mcp.tool()
def get_mapping_registry() -> dict:
    """
    Return all saved mapping configs from the persistent registry.

    Returns:
        Dict with registry_count and list of mapping summaries.
    """
    registry = _load_registry()
    summaries = [
        {
            "source_id":          v.get("source_id"),
            "detected_source":    v.get("detected_source"),
            "confidence":         v.get("confidence"),
            "column_fingerprint": k,
            "last_used":          v.get("last_used"),
            "use_count":          v.get("use_count", 0),
        }
        for k, v in registry.items()
    ]
    return {"registry_count": len(registry), "mappings": summaries}


@mcp.tool()
def save_mapping(source_id: str, mapping_config: dict) -> dict:
    """
    Persist a mapping config to the registry for future reuse.

    Args:
        source_id:      Human-readable identifier e.g. 'ga4_clickstream'.
        mapping_config: Full mapping config dict from detect_schema().

    Returns:
        Dict with status and saved fingerprint key.
    """
    fp = mapping_config.get("column_fingerprint")
    if not fp:
        return {"status": "error", "error": "mapping_config missing column_fingerprint — run detect_schema() first"}

    registry = _load_registry()
    mapping_config["source_id"] = source_id
    registry[fp] = mapping_config
    _save_registry(registry)

    log.info(f"Mapping saved: {source_id} (fingerprint: {fp})")
    return {"status": "saved", "fingerprint": fp, "source_id": source_id}


# ── Entry point ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    from cji.mcp_servers._serve import serve

    serve(mcp, "cji-ingestion-intelligence")