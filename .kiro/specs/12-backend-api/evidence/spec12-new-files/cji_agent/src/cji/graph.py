"""
CJI LangGraph definition
========================
Builds the (uncompiled) StateGraph:
  - nodes: supervisor plus the five workers in WORKER_NODES
  - conditional edges from supervisor via route(); every worker returns to supervisor
  - sequential: one successor per node, no fan-out (Spec 09, R11)

Checkpointing, the approval pause and resume are handled by cji.workflow.runtime (Spec 09), which compiles this
graph with the SQLite checkpointer and `interrupt_after=WORKER_NODES`.

Usage:
  from graph import build_graph
  graph = build_graph()                      # real workers
  graph = build_graph(nodes={...})           # replace workers (tests)
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from typing import Any

from langgraph.graph import END, START, StateGraph

from cji.agents.supervisor import route, supervisor
from cji.state import CJIState

logger = logging.getLogger("cji.graph")

# Worker nodes in pipeline order (route() decides which one runs next).
WORKER_NODES: tuple[str, ...] = (
    "ingestion_worker", "data_worker", "friction_worker", "insight_worker", "report_worker",
)

_base_graph = None


def _default_nodes() -> dict[str, Callable[..., Any]]:
    from cji.agents.ingestion_worker import ingestion_worker
    from cji.agents.workers import (
        data_worker,
        friction_worker,
        insight_worker,
        report_worker,
    )

    return {"ingestion_worker": ingestion_worker, "data_worker": data_worker, "friction_worker": friction_worker,
            "insight_worker": insight_worker, "report_worker": report_worker}


def build_graph(nodes: Mapping[str, Callable[..., Any]] | None = None) -> StateGraph:
    """The uncompiled CJI StateGraph. `nodes` replaces worker implementations by name (tests)."""
    workers = {**_default_nodes(), **dict(nodes or {})}
    unknown = set(workers) - set(WORKER_NODES)
    if unknown:
        raise ValueError(f"unknown worker nodes: {sorted(unknown)}")

    graph = StateGraph(CJIState)
    graph.add_node("supervisor", supervisor)
    for name in WORKER_NODES:
        graph.add_node(name, workers[name])
    graph.add_edge(START, "supervisor")
    graph.add_conditional_edges("supervisor", route, {**{name: name for name in WORKER_NODES}, "__end__": END})
    for name in WORKER_NODES:
        graph.add_edge(name, "supervisor")
    return graph


def get_base_graph() -> StateGraph:
    """The uncompiled graph with the real workers (cached)."""
    global _base_graph
    if _base_graph is None:
        _base_graph = build_graph()
    return _base_graph
