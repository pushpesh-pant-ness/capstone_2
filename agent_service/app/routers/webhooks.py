"""Receives Prometheus Alertmanager webhooks and kicks off a new incident run
for each firing alert (see infra/otel-demo alertmanager config -> this URL)."""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter

from .. import db, graph_runner
from ..schemas import AlertmanagerWebhook

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
        incident_id = await db.create_incident(alert_name, service_name, fault_id=None)
        asyncio.create_task(
            graph_runner.start_incident(
                str(incident_id), alert_name, service_name, alert.labels, alert.annotations
            )
        )
        started.append(str(incident_id))
        logger.info("started incident %s for alert %s (service=%s)", incident_id, alert_name, service_name)
    return {"started_incidents": started}
