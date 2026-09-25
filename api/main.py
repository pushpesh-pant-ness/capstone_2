"""FastAPI entrypoint — app bootstrap + DB connection pool (TASKS.md §2.3)."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

import db.repository as repo

from .routers import alerts, approvals, incidents

logging.basicConfig(level=logging.INFO)

UI_DIR = Path(__file__).resolve().parents[1] / "ui"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await repo.init_pool()
    yield
    await repo.close_pool()


app = FastAPI(title="Incident Remediation Agent", lifespan=lifespan)

app.include_router(alerts.router, tags=["alerts"])
app.include_router(incidents.router, tags=["incidents"])
app.include_router(approvals.router, tags=["approvals"])


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


if UI_DIR.exists():
    app.mount("/", StaticFiles(directory=str(UI_DIR), html=True), name="ui")
