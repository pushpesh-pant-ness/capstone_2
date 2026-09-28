"""Incident listing/detail + the live SSE timeline stream that the demo UI's
agent timeline panel connects to (ARCHITECTURE.md section 8.2)."""
from __future__ import annotations

import asyncio
import json
from uuid import UUID

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from .. import db
from ..events import bus

router = APIRouter()


@router.get("/incidents")
async def list_incidents(limit: int = 50):
    incidents = await db.list_incidents(limit=limit)
    return [_serialize_incident(i) for i in incidents]


@router.get("/incidents/{incident_id}")
async def get_incident(incident_id: UUID):
    incident = await db.get_incident(incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="incident not found")
    steps = await db.list_steps(incident_id)
    return {"incident": _serialize_incident(incident), "steps": [_serialize_step(s) for s in steps]}


@router.get("/incidents/{incident_id}/stream")
async def stream_incident(incident_id: UUID):
    queue = bus.subscribe(str(incident_id))

    async def event_generator():
        try:
            # Replay persisted steps first so a client connecting late still
            # sees the full history, then switch to live events.
            for step in await db.list_steps(incident_id):
                yield f"data: {json.dumps(_serialize_step(step), default=str)}\n\n"
            while True:
                event = await queue.get()
                yield event.to_sse()
        except asyncio.CancelledError:
            pass
        finally:
            bus.unsubscribe(str(incident_id), queue)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


def _serialize_incident(incident: dict) -> dict:
    return {k: (str(v) if not isinstance(v, (str, int, float, bool, type(None))) else v) for k, v in incident.items()}


def _serialize_step(step: dict) -> dict:
    return {k: (str(v) if not isinstance(v, (str, int, float, bool, type(None))) else v) for k, v in step.items()}
