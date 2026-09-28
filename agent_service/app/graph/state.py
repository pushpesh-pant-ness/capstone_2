"""LangGraph state shared across every node. See ARCHITECTURE.md section 5 (Agent
graph stages) for what each node does."""
from __future__ import annotations

from typing import Any, Optional, TypedDict


class AgentState(TypedDict, total=False):
    incident_id: str
    step_index: int

    alert_name: str
    service_name: Optional[str]
    labels: dict[str, str]
    annotations: dict[str, str]
    fault_id: Optional[str]  # matched from the fault registry, if recognized

    evidence: dict[str, Any]  # logs / metrics / traces gathered by `investigate`
    similar_incidents: list[dict[str, Any]]

    root_cause: str
    severity: str  # critical|warning|info

    plan: dict[str, Any]  # {"tool": str, "args": {...}, "justification": str}
    approval_status: str  # pending|approved|rejected
    approved_by: Optional[str]

    remediation_result: dict[str, Any]
    validation_result: dict[str, Any]  # {"recovered": bool, "details": {...}}
