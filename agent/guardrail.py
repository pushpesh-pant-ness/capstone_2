"""Deterministic plan sanity check (docs/AGENTS.md §4) — defense in depth on
top of the per-action allow-list filter already inside agent/nodes/plan.py.
Pure Python, no LLM, so the check doesn't depend on model behavior.
"""
from __future__ import annotations

from typing import Any, Optional

# Required params.py keys per allow-listed action (tools/allowlist.yaml /
# tools/k8s_tool.py signatures) — "namespace" deliberately excluded, it's
# always injected server-side (FR-18), never accepted from a plan.
REQUIRED_PARAMS: dict[str, set[str]] = {
    "restart_pod": {"deployment"},
    "rollback_deployment": {"deployment"},
    "scale_deployment": {"deployment", "replicas"},
}


def check_plan(
    plan: list[dict[str, Any]], *, allowed_namespace: str, max_actions: int = 3
) -> Optional[str]:
    """Returns None if the plan is safe to show a human, else an escalation reason."""
    if not plan or len(plan) > max_actions:
        return f"plan has {len(plan)} actions, expected 1-{max_actions}"
    for action in plan:
        params = action.get("params", {})
        if params.get("namespace", allowed_namespace) != allowed_namespace:
            return f"action targets namespace outside {allowed_namespace}"
        required = REQUIRED_PARAMS.get(action.get("name"))
        if required is not None and not required.issubset(params):
            missing = required - params.keys()
            return f"action '{action.get('name')}' missing required params: {sorted(missing)}"
    return None
