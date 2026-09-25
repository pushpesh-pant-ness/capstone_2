"""LangGraph wiring: Investigate -> Severity -> Historical -> RCA -> Plan
(BUILD_PLAN.md MVP definition #3). Remediation/Validation are NOT graph nodes —
they only run after a human approval decision, driven by api/routers/approvals.py
(FR-12..15), so there is nothing to interrupt/resume here.

agent/ never imports api/ or db/ (NFR-14) — historical candidates are fetched
by the caller and placed on the state before invoking this graph.
"""
from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from .nodes.historical import historical
from .nodes.investigate import investigate
from .nodes.plan import plan
from .nodes.rca import rca
from .nodes.severity import severity
from .state import AgentState


def build_graph():
    builder = StateGraph(AgentState)
    builder.add_node("investigate", investigate)
    # node id can't be "severity" — it collides with the AgentState "severity" key
    builder.add_node("assess_severity", severity)
    builder.add_node("historical", historical)
    builder.add_node("rca", rca)
    builder.add_node("plan", plan)

    builder.add_edge(START, "investigate")
    builder.add_edge("investigate", "assess_severity")
    builder.add_edge("assess_severity", "historical")
    builder.add_edge("historical", "rca")
    builder.add_edge("rca", "plan")
    builder.add_edge("plan", END)

    return builder.compile()


graph = build_graph()
