"""LangGraph wiring (docs/AGENTS.md §3, migration path §6): every incident
still starts with the same deterministic evidence gathering, but Supervisor
then routes it down one of two paths instead of forcing every incident
through the same RCA+Plan LLM calls:

    investigate -> assess_severity -> historical -> supervisor
    supervisor  -> auto_plan   (P4 + high-confidence, recovered historical match)
    supervisor  -> rca         (everything else)
    rca         -> escalate    (low_confidence)
    rca         -> plan        (otherwise)
    auto_plan / plan -> guardrail   (deterministic plan sanity check, defense in depth)
    guardrail   -> escalate    (guardrail rejects the plan)
    guardrail   -> END         (plan is fit to show a human)   <- HITL gate
    escalate    -> END                                         <- HITL gate

HITL (human-in-the-loop) is NOT a graph node — the graph's only job is to
reach END with either a pending_approval plan or an escalation_reason.
Remediation/Validation only run after a human approves via
api/routers/approvals.py (FR-12..15); the graph itself never resumes.

agent/ never imports api/ or db/ (NFR-14) — historical candidates are fetched
by the caller and placed on the state before invoking this graph.
"""
from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from .nodes.auto_plan import auto_plan
from .nodes.escalate import escalate
from .nodes.guardrail import guardrail, route_after_guardrail
from .nodes.historical import historical
from .nodes.investigate import investigate
from .nodes.plan import plan
from .nodes.rca import rca, route_after_rca
from .nodes.severity import severity
from .nodes.supervisor import route_after_supervisor, supervisor
from .state import AgentState


# Node ids as constants: avoids repeating/mistyping the same string across
# add_node/add_edge calls. ASSESS_SEVERITY can't be named "severity" — that
# collides with the AgentState "severity" key.
INVESTIGATE = "investigate"
ASSESS_SEVERITY = "assess_severity"
HISTORICAL = "historical"
SUPERVISOR = "supervisor"
AUTO_PLAN = "auto_plan"
RCA = "rca"
PLAN = "plan"
GUARDRAIL = "guardrail"
ESCALATE = "escalate"


def build_graph():
    builder = StateGraph(AgentState)
    builder.add_node(INVESTIGATE, investigate)
    builder.add_node(ASSESS_SEVERITY, severity)
    builder.add_node(HISTORICAL, historical)
    builder.add_node(SUPERVISOR, supervisor)
    builder.add_node(AUTO_PLAN, auto_plan)
    builder.add_node(RCA, rca)
    builder.add_node(PLAN, plan)
    builder.add_node(GUARDRAIL, guardrail)
    builder.add_node(ESCALATE, escalate)

    # Deterministic evidence-gathering chain — identical for every incident.
    builder.add_edge(START, INVESTIGATE)
    builder.add_edge(INVESTIGATE, ASSESS_SEVERITY)
    builder.add_edge(ASSESS_SEVERITY, HISTORICAL)
    builder.add_edge(HISTORICAL, SUPERVISOR)

    # Supervisor: replay a trusted historical plan, or fall through to RCA.
    builder.add_conditional_edges(
        SUPERVISOR, route_after_supervisor, {AUTO_PLAN: AUTO_PLAN, RCA: RCA}
    )
    # RCA: hand off to a human when confidence is too low to plan against.
    builder.add_conditional_edges(RCA, route_after_rca, {ESCALATE: ESCALATE, PLAN: PLAN})

    # Both planners converge on the same deterministic guardrail check.
    builder.add_edge(AUTO_PLAN, GUARDRAIL)
    builder.add_edge(PLAN, GUARDRAIL)
    # END here = pending_approval, waiting on the HITL gate in api/routers/approvals.py.
    builder.add_conditional_edges(
        GUARDRAIL, route_after_guardrail, {ESCALATE: ESCALATE, END: END}
    )
    builder.add_edge(ESCALATE, END)  # END here = escalated, also waiting on a human

    return builder.compile()


graph = build_graph()

