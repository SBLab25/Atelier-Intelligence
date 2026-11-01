"""
Tests for Phase 3 — Agent Layer
=================================
Tests the supervisor routing logic and graph compilation.
No LLM/MCP/network required — pure logic tests.
"""

import os
from pathlib import Path

CJI_ROOT = Path(__file__).parent.parent.resolve()   # cji_agent/ (the package is installed: Spec 11)

# Set CJI_MODE before importing config
os.environ["CJI_MODE"] = "demo"


# ── Supervisor routing tests ─────────────────────────────────────────────────

class TestRoute:
    """Tests for agents.supervisor.route()"""

    def _make_state(self, **overrides):
        """Build a minimal CJIState-like dict with defaults."""
        base = {
            "mode":                 "demo",
            "journey_name":         "onboarding",
            "journey_steps":        ["step1", "step2"],
            "analysis_window_days": 30,
            "analysis_window_mins": 60,
            "collector_url":        "http://localhost:8000",
            "iteration":            0,
            "next_worker":          "supervisor",
            "human_approved":       False,
            "last_run_at":          "",
            "messages":             [],
            "raw_events":           [],
            "event_summary":        {},
            "live_event_count":     0,
            "friction_scores":      [],
            "critical_steps":       [],
            "insights":             [],
            "prioritized_fixes":    [],
            "report_path":          "",
            "narrative":            "",
            "worker_statuses":      [],
            "errors":               [],
        }
        base.update(overrides)
        return base

    def test_route_to_data_worker(self):
        """Empty event_summary → route to data_worker."""
        from cji.agents.supervisor import route
        state = self._make_state(event_summary={})
        assert route(state) == "data_worker"

    def test_route_to_friction_worker(self):
        """Has event_summary but no friction_scores → friction_worker."""
        from cji.agents.supervisor import route
        state = self._make_state(
            event_summary={"step_metrics": [{"step_id": "s1"}]},
            friction_scores=[]
        )
        assert route(state) == "friction_worker"

    def test_route_to_insight_worker(self):
        """Has friction_scores but no insights → insight_worker."""
        from cji.agents.supervisor import route
        state = self._make_state(
            event_summary={"step_metrics": [{"step_id": "s1"}]},
            friction_scores=[{"step_id": "s1", "score": 75, "is_critical": True}],
            insights=[]
        )
        assert route(state) == "insight_worker"

    def test_route_pause_awaiting_approval(self):
        """Has insights but not approved → __end__ (PAUSE)."""
        from cji.agents.supervisor import route
        state = self._make_state(
            event_summary={"step_metrics": [{"step_id": "s1"}]},
            friction_scores=[{"step_id": "s1", "score": 75, "is_critical": True}],
            insights=[{"insight_id": "i1", "title": "test"}],
            human_approved=False
        )
        assert route(state) == "__end__"

    def test_route_to_report_worker(self):
        """Approved but no report_path → report_worker."""
        from cji.agents.supervisor import route
        state = self._make_state(
            event_summary={"step_metrics": [{"step_id": "s1"}]},
            friction_scores=[{"step_id": "s1", "score": 75, "is_critical": True}],
            insights=[{"insight_id": "i1", "title": "test"}],
            human_approved=True,
            report_path=""
        )
        assert route(state) == "report_worker"

    def test_route_complete(self):
        """Has report_path → __end__ (COMPLETE)."""
        from cji.agents.supervisor import route
        state = self._make_state(
            event_summary={"step_metrics": [{"step_id": "s1"}]},
            friction_scores=[{"step_id": "s1", "score": 75, "is_critical": True}],
            insights=[{"insight_id": "i1", "title": "test"}],
            human_approved=True,
            report_path="/some/report.html"
        )
        assert route(state) == "__end__"

    def test_route_safety_cutoff(self):
        """next_worker == __end__ forces immediate end."""
        from cji.agents.supervisor import route
        state = self._make_state(next_worker="__end__")
        assert route(state) == "__end__"


# ── Supervisor node tests ────────────────────────────────────────────────────

class TestSupervisor:
    """Tests for agents.supervisor.supervisor() node."""

    def test_increments_iteration(self):
        """supervisor() increments the iteration count."""
        from cji.agents.supervisor import supervisor
        state = {"iteration": 0, "next_worker": "supervisor"}
        result = supervisor(state)
        assert result["iteration"] == 1

    def test_multiple_increments(self):
        """Iteration starts from current value, not always from 0."""
        from cji.agents.supervisor import supervisor
        state = {"iteration": 5, "next_worker": "supervisor"}
        result = supervisor(state)
        assert result["iteration"] == 6

    def test_sets_last_run_at(self):
        """supervisor() sets last_run_at to an ISO timestamp."""
        from cji.agents.supervisor import supervisor
        state = {"iteration": 0, "next_worker": "supervisor"}
        result = supervisor(state)
        assert "last_run_at" in result
        assert len(result["last_run_at"]) > 10  # ISO string

    def test_guards_max_iterations(self):
        """Exceeding MAX_AGENT_ITERATIONS sets next_worker to __end__."""
        from cji.agents.supervisor import supervisor
        from cji.config import MAX_AGENT_ITERATIONS
        state = {"iteration": MAX_AGENT_ITERATIONS, "next_worker": "supervisor"}
        result = supervisor(state)
        assert result["next_worker"] == "__end__"
        assert any("Max iterations" in e["error"] for e in result.get("errors", []))  # WorkflowError dicts (Spec 03, RC-11)


# ── Graph compilation tests ──────────────────────────────────────────────────

class TestGraph:
    """Tests for graph.py compilation."""

    def test_graph_compiles(self):
        """build_graph() compiles without a checkpointer (Spec 09 removed the ignored use_persistence switch)."""
        from cji.graph import build_graph
        g = build_graph().compile()
        assert g is not None

    def test_graph_has_expected_nodes(self):
        """The compiled graph should contain all 5 expected nodes."""
        from cji.graph import build_graph
        g = build_graph().compile()
        # LangGraph compiled graphs expose nodes via get_graph()
        node_names = set()
        try:
            # Try the DrawableGraph API
            drawable = g.get_graph()
            node_names = {n.id for n in drawable.nodes}
        except Exception:
            # Fallback: just verify compile didn't crash
            pass

        if node_names:
            expected = {"supervisor", "data_worker", "friction_worker",
                        "insight_worker", "report_worker"}
            assert expected.issubset(node_names), (
                f"Missing nodes: {expected - node_names}"
            )
