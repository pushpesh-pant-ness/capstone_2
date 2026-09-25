"""Incident state schema (SRS.md §6.1), shared verbatim with api/models.py
(Phase 0 shared contract, TASKS.md §1). LangGraph carries this dict through
every node: Investigate -> Severity -> Historical -> RCA -> Plan.
"""
from __future__ import annotations

from typing import Any, Optional, TypedDict


class AgentState(TypedDict, total=False):
    # Identity / alert context
    incident_id: str
    alert_fingerprint: str
    title: str
    service_name: Optional[str]
    labels: dict[str, str]
    annotations: dict[str, str]

    # Investigate output (FR-4, FR-5, FR-6)
    evidence: dict[str, Any]           # {"logs": [...], "error_rate": ..., "p95_latency": ...}
    baseline: dict[str, Any]           # pre-incident metric snapshot, for Validation
    deployment_version: Optional[str]

    # Severity (FR-7)
    severity: str                      # P1..P4
    severity_rationale: str

    # Historical retrieval (FR-8) — candidates are fetched by the caller (api/
    # pipeline.py) via db/repository.py and placed on the state; agent/ itself
    # never imports db/ (NFR-14).
    historical_candidates: list[dict[str, Any]]
    similar_incidents: list[dict[str, Any]]

    # RCA (FR-9)
    root_cause_summary: str
    confidence_score: float
    low_confidence: bool

    # Plan (FR-10, FR-11)
    remediation_plan: list[dict[str, Any]]   # ordered list of {target, name, params, risk}

    # Escalation (docs/AGENTS.md §3 — supervisor/rca/guardrail handoff): set by
    # rca (low_confidence) or the guardrail node when a plan fails its sanity
    # check; presence signals the caller (api/pipeline.py) to mark the
    # incident escalated instead of pending_approval.
    escalation_reason: Optional[str]

    # Approval (FR-12..14) — set by the API, not by the graph itself
    approval_status: str                # pending|approved|rejected
    approved_by: Optional[str]

    # Remediation + Validation (FR-15..21)
    execution_results: list[dict[str, Any]]
    validation_result: dict[str, Any]   # {"recovered": bool, "evidence": {...}}
