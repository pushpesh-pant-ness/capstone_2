"""Alertmanager webhook intake (FR-1..FR-3). Responds within 5s by creating/
correlating the Incident row synchronously and kicking off the investigation
pipeline as a background task."""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter

import db.repository as repo
from agent.state import AgentState

from ..models import AlertmanagerWebhook
from ..pipeline import run_investigation

logger = logging.getLogger("incident-agent")
router = APIRouter()


def _service_name_from_labels(labels: dict[str, str]) -> str | None:
    return labels.get("service_name") or labels.get("service") or labels.get("job")


@router.post("/webhooks/alertmanager", status_code=202)
async def alertmanager_webhook(payload: AlertmanagerWebhook):
    started = []
    for alert in payload.alerts:
        if alert.status != "firing":
            continue
        alert_name = alert.labels.get("alertname", "UnknownAlert")
        service_name = _service_name_from_labels(alert.labels)
        # FR-3: correlate by Alertmanager's own fingerprint, not an invented one.
        fingerprint = alert.fingerprint or f"{alert_name}:{service_name}"

        incident_id = await repo.create_incident(
            alert_fingerprint=fingerprint,
            title=alert_name,
            description=alert.annotations.get("description") or alert.annotations.get("summary"),
            service_name=service_name,
        )
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
