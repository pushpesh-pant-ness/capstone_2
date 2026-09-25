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
    guardrail   -> END         (plan is fit to show a human)
    escalate    -> END

Remediation/Validation are NOT graph nodes — they only run after a human
approval decision, driven by api/routers/approvals.py (FR-12..15), so there is
nothing to interrupt/resume here.

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


def build_graph():
    builder = StateGraph(AgentState)
    builder.add_node("investigate", investigate)
    # node id can't be "severity" — it collides with the AgentState "severity" key
    builder.add_node("assess_severity", severity)
    builder.add_node("historical", historical)
    builder.add_node("supervisor", supervisor)
    builder.add_node("auto_plan", auto_plan)
    builder.add_node("rca", rca)
    builder.add_node("plan", plan)
    builder.add_node("guardrail", guardrail)
    builder.add_node("escalate", escalate)

    builder.add_edge(START, "investigate")
    builder.add_edge("investigate", "assess_severity")
    builder.add_edge("assess_severity", "historical")
    builder.add_edge("historical", "supervisor")
    builder.add_conditional_edges(
        "supervisor", route_after_supervisor, {"auto_plan": "auto_plan", "rca": "rca"}
    )
    builder.add_conditional_edges("rca", route_after_rca, {"escalate": "escalate", "plan": "plan"})
    builder.add_edge("auto_plan", "guardrail")
    builder.add_edge("plan", "guardrail")
    builder.add_conditional_edges("guardrail", route_after_guardrail, {"escalate": "escalate", END: END})
    builder.add_edge("escalate", END)

    return builder.compile()


graph = build_graph()

