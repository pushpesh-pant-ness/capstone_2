"""Guardrail node (docs/AGENTS.md §3-4): deterministic plan sanity check run
after any planner (auto_plan or plan), before a plan is persisted as
pending_approval. Hardens, rather than replaces, the per-action allow-list
filter already inside plan.py — defense in depth (FR-11, FR-15).
"""
from __future__ import annotations

import os
from typing import Any

from langgraph.graph import END

from ..guardrail import check_plan
from ..state import AgentState

# FR-18: same config-only namespace contract as api/pipeline.py's APP_NAMESPACE.
APP_NAMESPACE = os.environ.get("APP_NAMESPACE", "default")


async def guardrail(state: AgentState) -> dict[str, Any]:
    reason = check_plan(state.get("remediation_plan") or [], allowed_namespace=APP_NAMESPACE)
    return {"escalation_reason": reason} if reason else {}


def route_after_guardrail(state: AgentState) -> str:
    return "escalate" if state.get("escalation_reason") else END
