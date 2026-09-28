"""Builds the compiled LangGraph state machine.

Uses an in-memory checkpointer with `interrupt_before=["remediate"]` — this is
the actual mechanism implementing Human-in-the-Loop: the graph runs
detect -> investigate -> diagnose -> severity -> plan and then pauses. The
approvals router resumes it (or leaves it paused/escalated on rejection).

MemorySaver is process-local, which matches this being a single-replica demo
service (see events.py for the same constraint on the SSE event bus).
"""
from __future__ import annotations

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from . import nodes
from .state import AgentState

_checkpointer = MemorySaver()


def build_graph():
    builder = StateGraph(AgentState)
    builder.add_node("detect", nodes.detect)
    builder.add_node("investigate", nodes.investigate)
    builder.add_node("diagnose", nodes.diagnose)
    builder.add_node("assess_severity", nodes.assess_severity)
    builder.add_node("plan_remediation", nodes.plan)
    builder.add_node("remediate", nodes.remediate)
    builder.add_node("validate", nodes.validate)
    builder.add_node("resolve", nodes.resolve)

    builder.add_edge(START, "detect")
    builder.add_edge("detect", "investigate")
    builder.add_edge("investigate", "diagnose")
    builder.add_edge("diagnose", "assess_severity")
    builder.add_edge("assess_severity", "plan_remediation")
    builder.add_edge("plan_remediation", "remediate")
    builder.add_edge("remediate", "validate")
    builder.add_edge("validate", "resolve")
    builder.add_edge("resolve", END)

    return builder.compile(checkpointer=_checkpointer, interrupt_before=["remediate"])


graph = build_graph()
