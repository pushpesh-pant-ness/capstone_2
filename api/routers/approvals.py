"""Human approval endpoints — the actual HITL gate (FR-12..14). Nothing in
tools/k8s_tool.py runs until one of these is called."""
from __future__ import annotations

import asyncio
from uuid import UUID

from fastapi import APIRouter, HTTPException

import db.repository as repo

from ..models import ApprovalRequest, RejectionRequest
from ..pipeline import run_remediation_and_validation

router = APIRouter()


@router.post("/incidents/{incident_id}/approve", status_code=202)
async def approve_incident(incident_id: UUID, body: ApprovalRequest):
    incident = await repo.get_incident(incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="incident not found")
    if incident["status"] != "pending_approval":
        raise HTTPException(status_code=409, detail=f"incident is '{incident['status']}', not pending_approval")

    await repo.record_approval(incident_id, body.approved_by)
    await repo.log_audit_event(
        incident_id, "human", "approval_decision", {"decision": "approved", "by": body.approved_by, "comment": body.comment}
    )
    asyncio.create_task(run_remediation_and_validation(incident_id))
    return {"incident_id": str(incident_id), "status": "remediating"}


@router.post("/incidents/{incident_id}/reject", status_code=202)
async def reject_incident(incident_id: UUID, body: RejectionRequest):
    incident = await repo.get_incident(incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="incident not found")
    if incident["status"] != "pending_approval":
        raise HTTPException(status_code=409, detail=f"incident is '{incident['status']}', not pending_approval")

    # FR-14: rejection escalates; the Agent does not retry the same plan automatically.
    await repo.record_rejection(incident_id, body.rejected_by, body.reason)
    await repo.log_audit_event(
        incident_id, "human", "approval_decision", {"decision": "rejected", "by": body.rejected_by, "reason": body.reason}
    )
    return {"incident_id": str(incident_id), "status": "escalated"}
