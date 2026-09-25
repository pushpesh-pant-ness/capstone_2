"""Supervisor node (docs/AGENTS.md §3): pure rule-based router — no LLM —
deciding whether an incident can shortcut to auto_plan or needs the standard
RCA path. Deterministic so it's unit-testable without mocking an LLM.
"""
from __future__ import annotations

from typing import Any, Optional

from ..state import AgentState

AUTO_PLAN_SEVERITY = "P4"
AUTO_PLAN_SIMILARITY_THRESHOLD = 0.7


def find_auto_plan_candidate(state: AgentState) -> Optional[dict[str, Any]]:
    """A historical incident is replay-eligible only if it actually recovered
    (validation_result.recovered), scored high enough on the heuristic
    similarity (agent/heuristics.score_similar_incidents) to trust its plan
    wholesale, and left behind a non-empty remediation_plan.
    """
    if state.get("severity") != AUTO_PLAN_SEVERITY:
        return None
    for candidate in state.get("similar_incidents") or []:
        if candidate.get("similarity_score", 0.0) < AUTO_PLAN_SIMILARITY_THRESHOLD:
            continue
        if not candidate.get("remediation_plan"):
            continue
        if not (candidate.get("validation_result") or {}).get("recovered"):
            continue
        return candidate
    return None


async def supervisor(state: AgentState) -> dict[str, Any]:
    # No-op — routing happens in route_after_supervisor so the decision still
    # shows up as its own step in the audit log, same as every other node.
    return {}


def route_after_supervisor(state: AgentState) -> str:
    return "auto_plan" if find_auto_plan_candidate(state) is not None else "rca"
