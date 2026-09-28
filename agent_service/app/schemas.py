from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel


class AlertmanagerAlert(BaseModel):
    status: str
    labels: dict[str, str]
    annotations: dict[str, str] = {}
    startsAt: Optional[str] = None
    endsAt: Optional[str] = None


class AlertmanagerWebhook(BaseModel):
    version: Optional[str] = None
    status: str
    alerts: list[AlertmanagerAlert]


class ApprovalRequest(BaseModel):
    approved_by: str
    note: Optional[str] = None


class RejectionRequest(BaseModel):
    rejected_by: str
    reason: Optional[str] = None


class FaultTriggerResponse(BaseModel):
    fault_id: str
    message: str
