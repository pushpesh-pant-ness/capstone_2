"""Alertmanager webhook intake (FR-1..FR-3). Responds within 5s by creating/
correlating the Incident row synchronously and kicking off the investigation
pipeline as a background task."""
from __future__ import annotations

import asyncio
import hmac
import logging
import os

from fastapi import APIRouter, Header, HTTPException

import db.repository as repo
from agent.state import AgentState

from ..models import AlertmanagerWebhook
from ..pipeline import run_investigation

logger = logging.getLogger("incident-agent")
router = APIRouter()

# SRS §4.3: "Alertmanager -> Agent Intake uses an authenticated webhook". Unset
# by default for zero-config local dev, but anything reachable outside a
# trusted local network MUST set this (infra/alertmanager.yml's http_config
# sends it as a Bearer token) — otherwise anyone with network access could
# spawn arbitrary incidents/LLM calls against this endpoint.
ALERTMANAGER_WEBHOOK_TOKEN = os.environ.get("ALERTMANAGER_WEBHOOK_TOKEN")


def _service_name_from_labels(labels: dict[str, str]) -> str | None:
    return labels.get("service_name") or labels.get("service") or labels.get("job")


def _check_webhook_auth(authorization: str | None) -> None:
    if not ALERTMANAGER_WEBHOOK_TOKEN:
        return  # auth disabled — local dev default
    expected = f"Bearer {ALERTMANAGER_WEBHOOK_TOKEN}"
    if not authorization or not hmac.compare_digest(authorization, expected):
        raise HTTPException(status_code=401, detail="missing or invalid webhook credentials")


@router.post("/webhooks/alertmanager", status_code=202)
async def alertmanager_webhook(payload: AlertmanagerWebhook, authorization: str | None = Header(default=None)):
    _check_webhook_auth(authorization)
    started = []
    for alert in payload.alerts:
        if alert.status != "firing":
            continue
        alert_name = alert.labels.get("alertname", "UnknownAlert")
        service_name = _service_name_from_labels(alert.labels)
        # FR-3: correlate by Alertmanager's own fingerprint, not an invented one.
        fingerprint = alert.fingerprint or f"{alert_name}:{service_name}"

        incident_id, is_new = await repo.create_incident(
            alert_fingerprint=fingerprint,
            title=alert_name,
            description=alert.annotations.get("description") or alert.annotations.get("summary"),
            service_name=service_name,
        )
        if not is_new:
            # Alertmanager re-fired for a fingerprint that already has an open
            # incident (still investigating, awaiting approval, or being
            # remediated) — starting a second investigation here would race
            # the existing one and could silently clobber a human's approval
            # decision (see db.repository.create_incident docstring).
            logger.info(
                "alert %s (service=%s) already has an open incident %s — not starting another investigation",
                alert_name, service_name, incident_id,
            )
            continue
        initial_state: AgentState = {
            "incident_id": str(incident_id),
            "alert_fingerprint": fingerprint,
            "title": alert_name,
            "service_name": service_name,
            "labels": alert.labels,
            "annotations": alert.annotations,
        }
        asyncio.create_task(run_investigation(incident_id, initial_state))
        started.append(str(incident_id))
        logger.info("started incident %s for alert %s (service=%s)", incident_id, alert_name, service_name)
    return {"started_incidents": started}
