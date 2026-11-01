"""
Unit Tests: Supervisor Routing Logic
======================================
Tests the agents/supervisor.py module in isolation.

No LLM, no MCP, no database, no network.
All tests must pass in < 2 seconds.

Run:
  pytest tests/test_supervisor.py -v

Coverage targets:
  - route() routing logic: all 6 branches from 10-Development-Phases.md §5.3
  - supervisor() state updates: iteration increment, last_run_at, messages, errors
  - Safety cutoff: MAX_AGENT_ITERATIONS boundary
  - Auto-approve full pipeline: data → friction → insight → report → __end__
  - Pause path: data → friction → insight → __end__ (pause)
  - Edge cases: empty state, partial state, injection prevention
  - Integration: supervisor() + route() work together as graph.py expects
"""

from cji.agents.supervisor import supervisor, route, VALID_WORKERS


# ── Test Helper ────────────────────────────────────────────────────────────────

def _make_state(**overrides) -> dict:
    """
    Build a minimal CJIState-compatible dict with sensible defaults.

    All fields match the initial_state defined in main.py (lines 144-167).
    Override any field by passing it as a keyword argument.
    """
    base = {
        # Identity
        "mode":                 "demo",
        "journey_name":         "onboarding",
        "journey_steps":        ["landing_page", "sign_up_form", "email_verification",
                                 "profile_setup", "first_action", "completion"],
        # Configuration
        "analysis_window_days": 30,
        "analysis_window_mins": 60,
        "collector_url":        "http://localhost:8000",
        # Orchestration
        "iteration":            0,
        "next_worker":          "supervisor",
        "human_approved":       False,
        "last_run_at":          "",
        # Communication
        "messages":             [],
        # Data phase
        "raw_events":           [],
        "event_summary":        {},
        "live_event_count":     0,
        # Analysis phase
        "friction_scores":      [],
        "critical_steps":       [],
        # Insight phase
        "insights":             [],
        "prioritized_fixes":    [],
        # Delivery phase
        "report_path":          "",
        "narrative":            "",
        # Operations
        "worker_statuses":      [],
        "errors":               [],
    }
    base.update(overrides)
    return base


# ═══════════════════════════════════════════════════════════════════════════════
# SPEC VERIFICATION TEST (10-Development-Phases.md §5.3 lines 451-457)
# ═══════════════════════════════════════════════════════════════════════════════

class TestSpecVerification:
    """Exact test from the specification document."""

    def test_spec_route_empty_state_returns_data_worker(self):
        """EXACT test from 10-Development-Phases.md line 455:
        assert route(empty_state) == 'data_worker'
        """
        empty_state = {
            'event_summary': {}, 'friction_scores': [], 'insights': [],
            'human_approved': False, 'report_path': '', 'iteration': 0
        }
        assert route(empty_state) == 'data_worker', 'Routing failed'


# ═══════════════════════════════════════════════════════════════════════════════
# ROUTE() — ROUTING LOGIC (all 6 branches from spec §5.3 lines 440-446)
# ═══════════════════════════════════════════════════════════════════════════════

class TestRouteLogic:
    """Tests route() contains correct routing logic per spec."""

    def test_empty_event_summary_routes_to_data_worker(self):
        """Spec line 441: Empty event_summary → 'data_worker'."""
        state = _make_state(event_summary={})
        assert route(state) == "data_worker"

    def test_empty_friction_scores_routes_to_friction_worker(self):
        """Spec line 442: Empty friction_scores → 'friction_worker'."""
        state = _make_state(
            event_summary={"step_metrics": [{"step_id": "landing_page"}]},
            friction_scores=[],
        )
        assert route(state) == "friction_worker"

    def test_empty_insights_routes_to_insight_worker(self):
        """Spec line 443: Empty insights → 'insight_worker'."""
        state = _make_state(
            event_summary={"step_metrics": [{"step_id": "x"}]},
            friction_scores=[{"step_id": "x", "score": 87, "is_critical": True}],
            insights=[],
        )
        assert route(state) == "insight_worker"

    def test_insights_exist_not_approved_routes_to_end(self):
        """Spec line 444: Exists insights but human_approved False → '__end__' (PAUSE)."""
        state = _make_state(
            event_summary={"step_metrics": [{"step_id": "x"}]},
            friction_scores=[{"step_id": "x", "score": 87}],
            insights=[{"insight_id": "abc", "step_id": "x", "title": "Test"}],
            human_approved=False,
        )
        assert route(state) == "__end__"

    def test_approved_no_report_routes_to_report_worker(self):
        """Spec line 445: human_approved True but missing report_path → 'report_worker'."""
        state = _make_state(
            event_summary={"step_metrics": [{"step_id": "x"}]},
            friction_scores=[{"step_id": "x", "score": 80}],
            insights=[{"insight_id": "abc", "step_id": "x", "title": "Test"}],
            human_approved=True,
            report_path="",
        )
        assert route(state) == "report_worker"

    def test_else_routes_to_end(self):
        """Spec line 446: Else → '__end__'."""
        state = _make_state(
            event_summary={"step_metrics": [{"step_id": "x"}]},
            friction_scores=[{"step_id": "x", "score": 80}],
            insights=[{"insight_id": "abc"}],
            human_approved=True,
            report_path="/path/to/report.html",
        )
        assert route(state) == "__end__"


# ═══════════════════════════════════════════════════════════════════════════════
# SUPERVISOR() — ITERATION AND STATE UPDATES
# ═══════════════════════════════════════════════════════════════════════════════

class TestSupervisor:
    """Tests supervisor() increments iteration and delegates to route()."""

    def test_increments_iteration_by_one(self):
        """Spec line 439: supervisor increments 'iteration' by 1."""
        state = _make_state(iteration=0)
        assert supervisor(state)["iteration"] == 1

        state = _make_state(iteration=7)
        assert supervisor(state)["iteration"] == 8

    def test_sets_last_run_at_iso_format(self):
        """supervisor() must set last_run_at to an ISO-8601 timestamp."""
        result = supervisor(_make_state())
        ts = result["last_run_at"]
        assert ts, "last_run_at should not be empty"
        assert "T" in ts, f"Expected ISO-8601 format, got: {ts}"

    def test_no_errors_on_normal_routing(self):
        """Normal routing should NOT include errors."""
        result = supervisor(_make_state())
        assert "errors" not in result


# ═══════════════════════════════════════════════════════════════════════════════
# SAFETY CUTOFF
# ═══════════════════════════════════════════════════════════════════════════════

class TestSafetyCutoff:
    """Tests the MAX_AGENT_ITERATIONS safety guard."""

    def test_cutoff_at_max_iterations(self):
        """Supervisor ends at MAX_AGENT_ITERATIONS."""
        from cji.config import MAX_AGENT_ITERATIONS
        state = _make_state(iteration=MAX_AGENT_ITERATIONS)
        result = supervisor(state)
        assert result["next_worker"] == "__end__"


# ═══════════════════════════════════════════════════════════════════════════════
# AUTO-APPROVE PATH
# ═══════════════════════════════════════════════════════════════════════════════

class TestAutoApprovePath:
    """Tests routing when human_approved=True from the start."""

    def test_auto_approve_skips_pause_goes_to_report(self):
        """With auto-approve, after insights → report_worker (no pause)."""
        state = _make_state(
            event_summary={"step_metrics": [{"step_id": "x"}]},
            friction_scores=[{"step_id": "x", "score": 80}],
            insights=[{"insight_id": "abc"}],
            human_approved=True,
            report_path="",
        )
        assert route(state) == "report_worker"

    def test_auto_approve_full_pipeline(self):
        """Full pipeline with auto-approve: data→friction→insight→report→__end__."""
        state = _make_state(human_approved=True)

        assert route(state) == "data_worker"

        state["event_summary"] = {"step_metrics": [{"step_id": "x"}]}
        assert route(state) == "friction_worker"

        state["friction_scores"] = [{"step_id": "x", "score": 80}]
        assert route(state) == "insight_worker"

        state["insights"] = [{"insight_id": "abc"}]
        assert route(state) == "report_worker"

        state["report_path"] = "/path/to/report.html"
        assert route(state) == "__end__"


# ═══════════════════════════════════════════════════════════════════════════════
# VALID_WORKERS CONSTANT
# ═══════════════════════════════════════════════════════════════════════════════

class TestValidWorkers:
    """Tests the VALID_WORKERS constant."""

    def test_contains_all_expected_targets(self):
        """VALID_WORKERS must contain every route() target: 5 workers + __end__.

        v2.0 added ingestion_worker; this expectation predated it (Spec 02, U-4).
        """
        expected = {"ingestion_worker", "data_worker", "friction_worker",
                    "insight_worker", "report_worker", "__end__"}
        assert VALID_WORKERS == expected

    def test_is_frozenset(self):
        """VALID_WORKERS should be immutable."""
        assert isinstance(VALID_WORKERS, frozenset)


# ═══════════════════════════════════════════════════════════════════════════════
# EDGE CASES
# ═══════════════════════════════════════════════════════════════════════════════

class TestEdgeCases:
    """Tests unusual but possible state configurations."""

    def test_completely_empty_dict_routes_to_data(self):
        """Empty dict → data_worker (event_summary missing)."""
        assert route({}) == "data_worker"

    def test_event_summary_empty_dict_is_falsy(self):
        """event_summary={} is falsy → routes to data_worker."""
        assert route(_make_state(event_summary={})) == "data_worker"

    def test_event_summary_with_content_is_truthy(self):
        """event_summary={"x":1} is truthy → routes to friction_worker."""
        assert route(_make_state(event_summary={"step_metrics": []})) == "friction_worker"

    def test_friction_scores_empty_list_is_falsy(self):
        """friction_scores=[] is falsy → friction_worker."""
        state = _make_state(event_summary={"x": 1}, friction_scores=[])
        assert route(state) == "friction_worker"

    def test_insights_empty_list_is_falsy(self):
        """insights=[] is falsy → insight_worker."""
        state = _make_state(
            event_summary={"x": 1},
            friction_scores=[{"step_id": "x", "score": 20}],
            insights=[],
        )
        assert route(state) == "insight_worker"

    def test_report_path_empty_string_is_falsy(self):
        """report_path='' is falsy → report_worker after approval."""
        state = _make_state(
            event_summary={"x": 1},
            friction_scores=[{"step_id": "x"}],
            insights=[{"insight_id": "abc"}],
            human_approved=True,
            report_path="",
        )
        assert route(state) == "report_worker"

    def test_multiple_insights_still_pauses(self):
        """Pauses correctly with multiple insights."""
        state = _make_state(
            event_summary={"x": 1},
            friction_scores=[{"step_id": "x"}],
            insights=[{"id": "1"}, {"id": "2"}, {"id": "3"}],
            human_approved=False,
        )
        assert route(state) == "__end__"

    def test_errors_do_not_affect_routing(self):
        """Pre-existing errors don't change routing."""
        state = _make_state(
            errors=["data_worker: RuntimeError: fail"],
            event_summary={},
        )
        assert route(state) == "data_worker"

    def test_realtime_mode_routes_same_as_demo(self):
        """Routing is mode-agnostic."""
        for mode in ["demo", "realtime"]:
            assert route(_make_state(mode=mode)) == "data_worker"

    def test_iteration_default_is_zero(self):
        """Missing iteration key defaults to 0."""
        state = _make_state()
        del state["iteration"]
        result = supervisor(state)
        assert result["iteration"] == 1


# ═══════════════════════════════════════════════════════════════════════════════
# SUPERVISOR + ROUTE INTEGRATION
# ═══════════════════════════════════════════════════════════════════════════════

class TestSupervisorRouteIntegration:
    """Tests that supervisor() and route() work together."""

    def test_iteration_counts_across_cycles(self):
        """Iteration increments correctly across pipeline."""
        state = _make_state(human_approved=True)
        for expected in range(1, 6):
            update = supervisor(state)
            assert update["iteration"] == expected
            state.update(update)
            if expected == 1:
                state["event_summary"] = {"x": 1}
            elif expected == 2:
                state["friction_scores"] = [{"step_id": "x"}]
            elif expected == 3:
                state["insights"] = [{"id": "abc"}]
            elif expected == 4:
                state["report_path"] = "/path.html"


# ═══════════════════════════════════════════════════════════════════════════════
# FUNCTION SIGNATURES (spec compliance)
# ═══════════════════════════════════════════════════════════════════════════════

class TestFunctionSignatures:
    """Verifies functions match the spec's requirements."""

    def test_supervisor_is_sync(self):
        """Spec line 438: All functions must be synchronous def (NOT async)."""
        import asyncio
        assert not asyncio.iscoroutinefunction(supervisor)

    def test_route_is_sync(self):
        """route() must be synchronous for LangGraph conditional edges."""
        import asyncio
        assert not asyncio.iscoroutinefunction(route)

    def test_supervisor_returns_dict(self):
        """supervisor() must return dict."""
        result = supervisor(_make_state())
        assert isinstance(result, dict)

    def test_route_returns_str(self):
        """route() must return str."""
        result = route(_make_state())
        assert isinstance(result, str)
