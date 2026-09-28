"""FastAPI entrypoint — webhook receiver, HITL approval API, live SSE timeline,
fault-trigger API, and the static demo UI, all in one process (see
ARCHITECTURE.md: single live UI, no docker-compose, one deployable unit)."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from . import db
from .routers import approvals, faults, incidents, webhooks

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await db.init_pool()
    yield
    await db.close_pool()


app = FastAPI(title="Incident Remediation Agent", lifespan=lifespan)

app.include_router(webhooks.router, tags=["webhooks"])
app.include_router(incidents.router, tags=["incidents"])
app.include_router(approvals.router, tags=["approvals"])
app.include_router(faults.router, tags=["faults"])


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


app.mount("/", StaticFiles(directory="static", html=True), name="static")
