from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class AlertmanagerAlert(BaseModel):
    status: str
    labels: dict[str, str]
    annotations: dict[str, str] = {}
    startsAt: Optional[str] = None
    endsAt: Optional[str] = None
    fingerprint: Optional[str] = None  # Alertmanager's own dedup key (FR-3)
    generatorURL: Optional[str] = None


class AlertmanagerWebhook(BaseModel):
    version: Optional[str] = None
    status: str
    alerts: list[AlertmanagerAlert]


class ApprovalRequest(BaseModel):
    approved_by: str
    comment: Optional[str] = None


class RejectionRequest(BaseModel):
    rejected_by: str
    reason: Optional[str] = None
