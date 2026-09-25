"""Escalation node (docs/AGENTS.md §3): terminal for anything the pipeline
can't confidently propose a fix for (low RCA confidence, guardrail
rejection). Persisting status=escalated is the caller's job (api/pipeline.py)
— same NFR-14 boundary as every other node.
"""
from __future__ import annotations

from typing import Any

from ..state import AgentState


async def escalate(state: AgentState) -> dict[str, Any]:
    return {"escalation_reason": state.get("escalation_reason") or "escalated: reason not recorded"}
