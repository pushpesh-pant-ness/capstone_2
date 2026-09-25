"""Auto-plan shortcut (docs/AGENTS.md §3): for a P4 incident with a
high-confidence historical match that actually recovered, replay that
incident's remediation plan instead of spending an RCA + Plan LLM call
reinventing it.
"""
from __future__ import annotations

from typing import Any

from .supervisor import find_auto_plan_candidate
from ..state import AgentState


async def auto_plan(state: AgentState) -> dict[str, Any]:
    candidate = find_auto_plan_candidate(state)
    if candidate is None:
        # Shouldn't happen — route_after_supervisor only routes here when a
        # candidate exists — but escalate rather than silently plan nothing.
        return {"escalation_reason": "auto_plan: no matching historical candidate found"}
    return {
        "remediation_plan": candidate.get("remediation_plan") or [],
        "root_cause_summary": (
            f"Auto-replayed from resolved incident {candidate.get('incident_id')} "
            f"(same service/severity, similarity_score={candidate.get('similarity_score')})."
        ),
        "confidence_score": candidate.get("similarity_score", 0.0),
        "low_confidence": False,
    }
