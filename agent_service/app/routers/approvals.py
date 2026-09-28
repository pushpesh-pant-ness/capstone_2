"""Human approval endpoints — the actual HITL gate. Nothing in the remediate
node runs until one of these is called (see graph/build.py's interrupt_before)."""
from __future__ import annotations

import asyncio
from uuid import UUID

from fastapi import APIRouter, HTTPException

from .. import db, graph_runner
from ..schemas import ApprovalRequest, RejectionRequest

router = APIRouter()


@router.post("/incidents/{incident_id}/approve", status_code=202)
async def approve_incident(incident_id: UUID, body: ApprovalRequest):
    incident = await db.get_incident(incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="incident not found")
    if incident["status"] != "awaiting_approval":
        raise HTTPException(status_code=409, detail=f"incident is '{incident['status']}', not awaiting approval")
    asyncio.create_task(graph_runner.resume_after_decision(str(incident_id), approved=True, actor=body.approved_by))
    return {"incident_id": str(incident_id), "status": "remediating"}


@router.post("/incidents/{incident_id}/reject", status_code=202)
async def reject_incident(incident_id: UUID, body: RejectionRequest):
    incident = await db.get_incident(incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="incident not found")
    if incident["status"] != "awaiting_approval":
        raise HTTPException(status_code=409, detail=f"incident is '{incident['status']}', not awaiting approval")
    asyncio.create_task(graph_runner.resume_after_decision(str(incident_id), approved=False, actor=body.rejected_by))
    return {"incident_id": str(incident_id), "status": "escalated"}
