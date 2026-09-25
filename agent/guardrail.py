"""Deterministic plan sanity check (docs/AGENTS.md §4) — defense in depth on
top of the per-action allow-list filter already inside agent/nodes/plan.py.
Pure Python, no LLM, so the check doesn't depend on model behavior.
"""
from __future__ import annotations

from typing import Any, Optional


def check_plan(
    plan: list[dict[str, Any]], *, allowed_namespace: str, max_actions: int = 3
) -> Optional[str]:
    """Returns None if the plan is safe to show a human, else an escalation reason."""
    if not plan or len(plan) > max_actions:
        return f"plan has {len(plan)} actions, expected 1-{max_actions}"
    for action in plan:
        if action.get("params", {}).get("namespace", allowed_namespace) != allowed_namespace:
            return f"action targets namespace outside {allowed_namespace}"
    return None
