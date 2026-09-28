"""Glue between the FastAPI routers and the compiled LangGraph graph: starting a
new incident run, and resuming it after a human approval/rejection decision.
"""
from __future__ import annotations

import json
from uuid import UUID

from . import db
from .graph.build import graph
from .graph.state import AgentState


async def start_incident(
    incident_id: str,
    alert_name: str,
    service_name: str | None,
    labels: dict,
    annotations: dict,
) -> None:
    state: AgentState = {
        "incident_id": incident_id,
        "alert_name": alert_name,
        "service_name": service_name,
        "labels": labels,
        "annotations": annotations,
    }
    cfg = {"configurable": {"thread_id": incident_id}}
    try:
        await graph.ainvoke(state, config=cfg)
    except Exception as exc:
        await db.update_incident(UUID(incident_id), status="escalated", summary=f"Agent error: {exc}")
        return

    snapshot = await graph.aget_state(cfg)
    values = snapshot.values if snapshot else {}
    plan = values.get("plan")
    await db.update_incident(
        UUID(incident_id),
        status="awaiting_approval",
        summary=values.get("root_cause"),
        root_cause=values.get("root_cause"),
        severity=values.get("severity"),
        remediation_plan=json.dumps(plan) if plan else None,
    )


async def resume_after_decision(incident_id: str, approved: bool, actor: str) -> None:
    cfg = {"configurable": {"thread_id": incident_id}}
    incident_uuid = UUID(incident_id)

    if not approved:
        await db.update_incident(incident_uuid, status="escalated", approved_by=actor)
        return

    await db.mark_approved(incident_uuid, actor)
    try:
        await graph.ainvoke(None, config=cfg)
    except Exception as exc:
        await db.update_incident(
            incident_uuid, status="escalated", summary=f"Agent error during remediation: {exc}"
        )
