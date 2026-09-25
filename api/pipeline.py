"""Shared pipeline glue — invoked identically by api/routers/alerts.py and by
scripts/run_agent_cli.py (BUILD_PLAN.md design principle #3: one pipeline, two
entry points). This is the ONLY place that wires agent/ (pure graph) to db/
(persistence) and tools/ (execution) — agent/ itself never imports db or api
(NFR-14).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any
from uuid import UUID

import yaml

import db.repository as repo
from agent.graph import graph
from agent.state import AgentState
from tools.k8s_tool import k8s_tool
from tools.prometheus_tool import prometheus_tool

logger = logging.getLogger("incident-agent")

VALIDATION_WINDOW_SECONDS = int(os.environ.get("VALIDATION_WINDOW_SECONDS", "180"))
VALIDATION_POLL_SECONDS = int(os.environ.get("VALIDATION_POLL_SECONDS", "15"))
# FR-18: the K8s target namespace is only ever taken from config, never inferred.
# Plan actions (LLM or heuristic fallback, see agent/heuristics.py) don't include
# a namespace, so the executor supplies this default unless a plan overrides it.
APP_NAMESPACE = os.environ.get("APP_NAMESPACE", "default")
_ALLOWLIST_PATH = Path(__file__).resolve().parents[1] / "tools" / "allowlist.yaml"


def _allowed_action_names() -> set[str]:
    with open(_ALLOWLIST_PATH, "r", encoding="utf-8") as f:
        doc = yaml.safe_load(f)
    return {t["name"] for t in doc["tools"]}


def _dry_run_enabled() -> bool:
    return os.environ.get("DRY_RUN", "false").lower() == "true"


def _as_dict(value: Any) -> dict:
    if isinstance(value, str):
        return json.loads(value) if value else {}
    return value or {}


def _as_list(value: Any) -> list:
    if isinstance(value, str):
        return json.loads(value) if value else []
    return value or []


async def run_investigation(incident_id: UUID, initial_state: AgentState) -> None:
    """Investigate -> Severity -> Historical -> RCA -> Plan (FR-4..FR-11),
    persisting each node's output and an audit_log entry as it completes so the
    incident detail view can reconstruct the full timeline (FR-23)."""
    await repo.update_incident(incident_id, status="investigating")
    await repo.log_audit_event(incident_id, "system", "state_transition", {"status": "investigating"})

    initial_state["historical_candidates"] = await repo.list_resolved_incidents()

    state: dict[str, Any] = dict(initial_state)
    try:
        async for update in graph.astream(initial_state, stream_mode="updates"):
            for node_name, partial in update.items():
                state.update(partial)
                action_type = "llm_call" if node_name in ("severity", "rca", "plan") else "tool_call"
                await repo.log_audit_event(incident_id, "agent", action_type, {"node": node_name, "output": partial})
    except Exception as exc:  # noqa: BLE001
        logger.exception("investigation pipeline failed for incident %s", incident_id)
        await repo.update_incident(incident_id, status="escalated")
        await repo.log_audit_event(
            incident_id, "system", "state_transition", {"status": "escalated", "error": str(exc)}
        )
        return

    similar_ids = [c["incident_id"] for c in state.get("similar_incidents", []) if c.get("incident_id")]
    await repo.update_incident(
        incident_id,
        status="pending_approval",
        deployment_version=state.get("deployment_version"),
        evidence=state.get("evidence"),
        baseline=state.get("baseline"),
        severity=state.get("severity"),
        root_cause_summary=state.get("root_cause_summary"),
        confidence_score=state.get("confidence_score"),
        remediation_plan=state.get("remediation_plan"),
        similar_incident_ids=similar_ids,
    )
    await repo.log_audit_event(incident_id, "system", "state_transition", {"status": "pending_approval"})


async def run_remediation_and_validation(incident_id: UUID) -> None:
    """Executor (FR-15..18) + bounded validation loop (FR-19..21). Only ever
    called after a human approval decision (api/routers/approvals.py)."""
    incident = await repo.get_incident(incident_id)
    if incident is None:
        return

    plan = _as_list(incident.get("remediation_plan"))
    allowed = _allowed_action_names()

    await repo.update_incident(incident_id, status="remediating")
    await repo.log_audit_event(incident_id, "system", "state_transition", {"status": "remediating"})

    execution_results = []
    for action in plan:
        if action.get("name") not in allowed:
            # FR-15: re-checked independently of the Planning node's own filtering.
            result = {"error": f"action '{action.get('name')}' is not on tools/allowlist.yaml — refused"}
        else:
            try:
                params = {"namespace": APP_NAMESPACE, **action.get("params", {})}
                result = k8s_tool.call(action["name"], dry_run=_dry_run_enabled(), **params)
            except Exception as exc:  # noqa: BLE001
                result = {"error": str(exc)}
        execution_results.append({"action": action, "result": result})
        await repo.log_audit_event(incident_id, "agent", "tool_call", {"action": action, "result": result})

    await repo.update_incident(incident_id, status="validating")
    await repo.log_audit_event(incident_id, "system", "state_transition", {"status": "validating"})

    validation_result = await _validate_recovery(incident)
    validation_result["execution_results"] = execution_results

    final_status = "resolved" if validation_result["recovered"] else "escalated"
    await repo.mark_resolution(incident_id, final_status, validation_result)
    await repo.log_audit_event(
        incident_id, "system", "state_transition", {"status": final_status, "validation": validation_result}
    )


async def _validate_recovery(incident: dict[str, Any]) -> dict[str, Any]:
    baseline = _as_dict(incident.get("baseline"))
    service = incident.get("service_name") or ""
    baseline_error_rate = baseline.get("error_rate") or 0.0

    loop = asyncio.get_running_loop()
    deadline = loop.time() + VALIDATION_WINDOW_SECONDS
    details: dict[str, Any] = {}
    recovered = False
    while loop.time() < deadline:
        try:
            error_rate = prometheus_tool.error_rate(service)
            details = {"error_rate": error_rate, "baseline_error_rate": baseline_error_rate}
            if error_rate <= max(0.01, baseline_error_rate * 0.2):
                recovered = True
                break
        except Exception as exc:  # noqa: BLE001
            details = {"error": str(exc)}
        await asyncio.sleep(VALIDATION_POLL_SECONDS)

    return {"recovered": recovered, "evidence": details}
