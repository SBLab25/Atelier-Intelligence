"""
Contract tests for Spec 03 (canonical domain contracts).

Every concept has one definition in domain/; old import paths re-export it.
All tests run offline: no database, no network, no LLM.
"""
import ast
import asyncio
import contextlib
import importlib
import inspect
import json
import os
import subprocess
import sys
from pathlib import Path

import pandas as pd  # type: ignore[import-untyped]
import pytest
from pydantic import ValidationError

APP_ROOT = Path(__file__).resolve().parent.parent
PARQUET = APP_ROOT / "data" / "events.parquet"

# Exact shape produced by tracker.js makeEvent() (wire format v1).
TRACKER_WIRE = {
    "timestamp": "2026-10-27T10:15:30.123Z",
    "event_id": "evt-0b1e7a2c-4f1d-4c3a",
    "session_id": "sess-1234abcd",
    "user_id": "user-5678efgh",
    "journey_name": "user_onboarding",
    "step_id": "sign_up_form",
    "event_type": "click",
    "url": "https://app.example.test/signup?email=a@b.test#top",
    "element_selectors": "button#submit",
    "metadata": {"click_x": 10, "click_y": 20},
}
TAXONOMY = frozenset({"page_view", "click", "form_submit", "error",
                      "rage_click", "abandon", "step_complete", "identify"})


def run(value):
    return asyncio.run(value) if inspect.isawaitable(value) else value


# ═════════════════════════════════════════════════════════════════════════════
# Single source of truth
# ═════════════════════════════════════════════════════════════════════════════

def test_event_taxonomy_has_one_definition_and_is_unchanged():
    import collector.models as cm
    from domain.events import ALLOWED_EVENT_TYPES
    from mcp_servers import ingestion_intelligence_server as ing
    from tools import ingest_json as ij

    assert ALLOWED_EVENT_TYPES == TAXONOMY
    assert cm.ALLOWED_EVENT_TYPES is ALLOWED_EVENT_TYPES
    assert ing.ALLOWED_EVENT_TYPES is ALLOWED_EVENT_TYPES
    assert set(ing.CANONICAL_SCHEMA["allowed_event_types"]) == ALLOWED_EVENT_TYPES
    assert ij.VALID_EVENT_TYPES is ALLOWED_EVENT_TYPES


def test_old_import_paths_reexport_domain_objects():
    import agents.supervisor as sup
    import collector.models as cm
    import guardrails.output_validator as ov
    import state
    from domain import events, insights, metrics, runs

    assert cm.TrackerEvent is events.TrackerEvent
    assert cm.EventBatch is events.EventBatch
    assert state.JourneyEvent is events.EventRecord
    assert state.StepMetrics is metrics.StepMetrics
    assert state.FrictionScore is metrics.FrictionScore
    assert state.Insight is insights.Insight
    assert state.WorkerStatus is runs.WorkerStatus
    assert state.IngestionResult is runs.IngestionResult
    assert sup.VALID_WORKERS is runs.VALID_WORKERS
    assert ov.VALID_CATEGORIES is insights.INSIGHT_CATEGORIES
    assert ov.VALID_EFFORTS is insights.FIX_EFFORTS


def test_collector_api_has_no_private_event_models():
    api = importlib.import_module("collector.api")
    assert not hasattr(api, "EventItem")
    assert not hasattr(api, "BatchPayload")


def test_domain_imports_only_pydantic_and_stdlib():
    allowed = set(sys.stdlib_module_names) | {"pydantic", "typing_extensions"}
    for path in sorted((APP_ROOT / "domain").glob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                names = [node.module or ""]
            else:
                continue
            for name in names:
                assert name.split(".")[0] in allowed, f"{path.name} imports {name}"


# ═════════════════════════════════════════════════════════════════════════════
# Browser events: wire compatibility, invalid input, round trips
# ═════════════════════════════════════════════════════════════════════════════

def test_tracker_wire_and_documented_forms_give_the_same_record():
    from domain.events import TrackerEvent, to_record

    wire = to_record(TrackerEvent.model_validate(TRACKER_WIRE))
    documented = {k: v for k, v in TRACKER_WIRE.items() if k not in ("journey_name", "element_selectors")}
    doc = to_record(TrackerEvent.model_validate({**documented, "journey_id": "user_onboarding"}))

    assert wire == doc
    assert wire["journey_id"] == "user_onboarding"
    assert wire["duration_ms"] == 0
    assert wire["url"] == "https://app.example.test/signup"


def test_live_events_row_keeps_the_table_layout():
    from domain.events import TrackerEvent, to_live_events_row

    row = to_live_events_row(TrackerEvent.model_validate(TRACKER_WIRE))
    assert set(row) == {"timestamp", "event_id", "session_id", "user_id", "journey_name",
                        "step_id", "event_type", "url", "element_selectors", "metadata"}
    assert row["journey_name"] == "user_onboarding"
    assert row["element_selectors"] == "button#submit"
    assert json.loads(row["metadata"]) == {"click_x": 10, "click_y": 20}


@pytest.mark.parametrize("field, value", [
    ("event_type", "scroll"),
    ("event_type", "PAGE_VIEW"),
    ("duration_ms", -1),
    ("timestamp", "yesterday"),
    ("step_id", ""),
    ("step_id", "bad\x00step"),
    ("journey_name", "   "),
    ("event_id", "short"),
])
def test_invalid_browser_events_are_rejected(field, value):
    from domain.events import TrackerEvent

    with pytest.raises(ValidationError):
        TrackerEvent.model_validate({**TRACKER_WIRE, field: value})


@pytest.mark.parametrize("count", [0, 101])
def test_batch_size_limits(count):
    from domain.events import EventBatch

    with pytest.raises(ValidationError):
        EventBatch.model_validate({"api_key": "cji_dev_localtest", "events": [TRACKER_WIRE] * count})


def test_event_record_json_round_trip_is_lossless():
    from domain.events import EVENT_RECORD, TrackerEvent, to_record

    record = to_record(TrackerEvent.model_validate(TRACKER_WIRE))
    assert EVENT_RECORD.validate_json(json.dumps(record)) == record


def test_collector_rejects_invalid_events_and_stores_valid_ones(monkeypatch, pg_url):
    # PostgreSQL since Spec 07: the collector writes one multi-row INSERT ... RETURNING (OD-41).
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine, text

    api = importlib.import_module("collector.api")
    engine = create_engine(pg_url)
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS live_events, api_keys"))
    monkeypatch.setattr(api, "engine", engine)
    monkeypatch.setattr(api, "CJI_ENV", "development")          # seeds cji_dev_localtest
    monkeypatch.setattr(api, "JOURNEY_NAME", "user_onboarding")
    api._create_tables()
    client = TestClient(api.app, raise_server_exceptions=False)

    bad = client.post("/collect/batch", json={"api_key": "cji_dev_localtest",
                                              "events": [{**TRACKER_WIRE, "event_type": "scroll"}]})
    assert bad.status_code == 422

    events = [{**TRACKER_WIRE, "event_id": f"{TRACKER_WIRE['event_id']}-{i:02d}"} for i in range(20)]
    good = client.post("/collect/batch", json={"api_key": "cji_dev_localtest", "events": events})
    assert good.status_code == 200 and good.json()["accepted"] == 20
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT journey_name, url FROM live_events")).fetchall()
    engine.dispose()
    assert len(rows) == 20
    assert rows[0][0] == "user_onboarding"
    assert rows[0][1] == "https://app.example.test/signup"


# ═════════════════════════════════════════════════════════════════════════════
# Stored events and analytics records against real outputs
# ═════════════════════════════════════════════════════════════════════════════

def test_tracked_parquet_rows_are_valid_event_records():
    from domain.events import EVENT_RECORDS

    df = pd.read_parquet(PARQUET).head(200)
    rows = json.loads(df.to_json(orient="records", date_format="iso"))
    EVENT_RECORDS.validate_python(rows)


def test_journey_data_and_friction_outputs_match_contracts(monkeypatch):
    from config import JOURNEY_CONFIG
    from domain.metrics import FRICTION_SCORES, FUNNEL_RESULT, STEP_METRICS_LIST
    from mcp_servers import journey_data_server as j
    from mcp_servers.friction_engine_server import score_all_steps

    # Demo is the configured mode in tests; the repository is chosen from settings (Spec 05).
    monkeypatch.setattr(j, "JOURNEY_CONFIG", {"name": "user_onboarding", "steps": JOURNEY_CONFIG["steps"]})
    metrics = run(j.get_step_metrics())["step_metrics"]
    assert len(metrics) == 8
    STEP_METRICS_LIST.validate_python(metrics)
    FUNNEL_RESULT.validate_python(run(j.get_funnel_dropoff()))
    FRICTION_SCORES.validate_python(score_all_steps(metrics)["scores"])


def test_validator_and_fallback_outputs_are_insight_drafts():
    from domain.insights import INSIGHT_DRAFT
    from guardrails.output_validator import _fallback, validate_llm_output

    INSIGHT_DRAFT.validate_python(validate_llm_output({"title": "Slow form"}, "sign_up_form"))
    INSIGHT_DRAFT.validate_python(validate_llm_output("not a dict", "sign_up_form"))
    INSIGHT_DRAFT.validate_python(_fallback("sign_up_form", "message"))


def test_prioritised_insight_matches_contract():
    from domain.insights import INSIGHT
    from guardrails.output_validator import _fallback
    from mcp_servers.insight_server import prioritise_fix

    draft = {**_fallback("sign_up_form", "m"), "insight_id": "ins-1", "score": 80}
    INSIGHT.validate_python(prioritise_fix(draft, 120))


def test_report_outputs_match_contracts(monkeypatch, tmp_path):
    from domain.insights import NARRATIVE, REPORT_RESULT
    from integrations import LLMGateway
    from integrations.testing import MemoryAuditSink
    from mcp_servers import report_server as rs

    monkeypatch.setattr(rs, "REPORTS_DIR", tmp_path)
    # Spec 08: LLM disabled -> the deterministic narrative; the gateway metadata is not part of NARRATIVE.
    monkeypatch.setattr(rs, "_llm", LLMGateway(provider="none", model="", api_key=None, service="test",
                                               audit=MemoryAuditSink()))
    REPORT_RESULT.validate_python(rs.export_report(journey_name="j", narrative="n", friction_scores=[],
                                                   insights=[], funnel_data=[], mode="demo"))
    out = asyncio.run(rs.generate_narrative(insights=[], journey_name="j", avg_score=1.0,
                                            critical_count=0, mode="demo"))
    assert out["llm"]["code"] == "llm_disabled"
    NARRATIVE.validate_python({k: v for k, v in out.items() if k != "llm"})


# ═════════════════════════════════════════════════════════════════════════════
# Ingestion adapters
# ═════════════════════════════════════════════════════════════════════════════

def test_file_ingestion_counts_coerced_types_and_emits_event_records(tmp_path):
    from domain.events import EVENT_RECORD
    from mcp_servers.ingestion_intelligence_server import apply_mapping

    path = tmp_path / "src.csv"
    pd.DataFrame({
        "event_name": ["scroll", "page_view", "weird"],
        "user": ["u1", "u2", "u3"],
        "ts": ["2026-01-01T00:00:00Z"] * 3,
        "page": ["https://x.test/signup?a=1", "https://x.test/verify", "https://x.test/done"],
    }).to_csv(path, index=False)
    mapping = {"field_mapping": {"event_name": "event_type", "user": "user_id", "ts": "timestamp", "page": "url"}}
    result = apply_mapping(str(path), mapping)

    assert result["records_coerced"] == 2
    assert result["records_passed"] == 3
    for record in result["_records_internal"]:
        EVENT_RECORD.validate_python(record)


def test_ingest_json_maps_aliases_and_skips_unknown_types():
    from tools.ingest_json import _finalise

    df = pd.DataFrame({
        "event_type": ["drop_off", "session_start", "scroll", "click"],
        "user_id": ["u1"] * 4,
        "timestamp": ["2026-01-01T00:00:00Z"] * 4,
    })
    assert list(_finalise(df)["event_type"]) == ["abandon", "page_view", "click"]


# ═════════════════════════════════════════════════════════════════════════════
# Journey identifiers
# ═════════════════════════════════════════════════════════════════════════════

def test_journey_definition_validates_config():
    from config import JOURNEY_CONFIG
    from domain.journeys import journey_from_config

    assert len(journey_from_config(JOURNEY_CONFIG).steps) == 8
    for bad in ({"name": "", "steps": ["a"]}, {"name": "x", "steps": []},
                {"name": "x", "steps": ["a", "a"]}, {"name": "x\ny", "steps": ["a"]}):
        with pytest.raises(ValidationError):
            journey_from_config(bad)


def test_default_journey_matches_the_tracked_data():
    script = ("import dotenv; dotenv.load_dotenv = lambda *a, **k: False; "
              "import config; print(config.JOURNEY_NAME)")
    env = {k: v for k, v in os.environ.items() if k != "JOURNEY_NAME"}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    out = subprocess.run([sys.executable, "-c", script], cwd=APP_ROOT, env=env,
                         capture_output=True, text=True, timeout=120, check=False)
    assert out.stdout.strip().splitlines()[-1] == "user_onboarding", out.stderr[-500:]
    assert set(pd.read_parquet(PARQUET, columns=["journey_id"])["journey_id"]) == {"user_onboarding"}


# ═════════════════════════════════════════════════════════════════════════════
# Workflow status, errors, and worker-boundary checks
# ═════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("status", ["success", "error", "skipped", "partial"])
def test_worker_status_values_include_ingestion_statuses(status):
    from domain.runs import WORKER_STATUS

    WORKER_STATUS.validate_python({"worker": "ingestion_worker", "status": status, "message": "m"})


def test_unknown_worker_status_is_rejected():
    from domain.runs import WORKER_STATUS

    with pytest.raises(ValidationError):
        WORKER_STATUS.validate_python({"worker": "data_worker", "status": "done", "message": "m"})


def test_supervisor_cutoff_error_is_a_workflow_error(monkeypatch):
    import agents.supervisor as sup
    from domain.runs import WORKFLOW_ERRORS

    monkeypatch.setattr(sup, "MAX_AGENT_ITERATIONS", 1)
    out = sup.supervisor({"iteration": 5})
    WORKFLOW_ERRORS.validate_python(out["errors"])
    assert out["errors"][0]["worker"] == "supervisor"


def _fake_tools(monkeypatch, module, payload):
    @contextlib.asynccontextmanager
    async def fake_session(name):
        yield object()

    async def fake_call_tool(session, tool, arguments=None):
        return payload

    monkeypatch.setattr(module, "mcp_session", fake_session)
    monkeypatch.setattr(module, "call_tool", fake_call_tool)


def test_malformed_mcp_result_becomes_a_recorded_error(monkeypatch):
    import agents.workers as w
    from domain.runs import WORKFLOW_ERRORS

    bad_scores = [{"step_id": "sign_up_form", "score": "not-a-number"}]
    _fake_tools(monkeypatch, w, {"scores": bad_scores})
    out = run(w.friction_worker({"event_summary": {"step_metrics": [{"step_id": "sign_up_form"}]}}))

    assert out["friction_scores"] == bad_scores          # passed through unchanged
    WORKFLOW_ERRORS.validate_python(out["errors"])
    assert out["errors"][0]["worker"] == "friction_worker"
    assert "contract" in out["errors"][0]["error"]


def test_valid_mcp_result_adds_no_error(monkeypatch):
    import agents.workers as w

    good = [{"step_id": "s", "score": 70, "drop_off_rate": 0.4, "avg_dwell_ms": 1000, "retry_count": 0.5,
             "rage_click_rate": 0.1, "signals": ["high_drop_off"], "confidence": 0.6, "is_critical": True}]
    _fake_tools(monkeypatch, w, {"scores": good})
    out = run(w.friction_worker({"event_summary": {"step_metrics": [{"step_id": "s"}]}}))
    assert "errors" not in out
    assert out["critical_steps"] == ["s"]
