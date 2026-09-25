"""Incident list/detail + audit log viewer (FR-23, §4.1)."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException

import db.repository as repo

router = APIRouter()


def _serialize(row: dict) -> dict:
    return {k: (str(v) if not isinstance(v, (str, int, float, bool, type(None), list, dict)) else v) for k, v in row.items()}


@router.get("/incidents")
async def list_incidents(status: str | None = None, limit: int = 50):
    incidents = await repo.list_incidents(status=status, limit=limit)
    return [_serialize(i) for i in incidents]


@router.get("/incidents/{incident_id}")
async def get_incident(incident_id: UUID):
    incident = await repo.get_incident(incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="incident not found")
    return _serialize(incident)


@router.get("/incidents/{incident_id}/audit")
async def get_audit_log(incident_id: UUID):
    incident = await repo.get_incident(incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="incident not found")
    entries = await repo.list_audit_log(incident_id)
    return [_serialize(e) for e in entries]
