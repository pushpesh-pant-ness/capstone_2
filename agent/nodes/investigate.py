"""Investigate node (FR-4, FR-5, FR-6): pulls Loki logs + Prometheus metrics for
the affected service and the last deployed image tag/commit, before Severity runs.
"""
from __future__ import annotations

import os
from typing import Any

from tools.k8s_tool import get_deployment_image_tag
from tools.loki_tool import loki_tool
from tools.prometheus_tool import prometheus_tool

from ..state import AgentState

APP_NAMESPACE = os.environ.get("APP_NAMESPACE", "default")


async def investigate(state: AgentState) -> dict[str, Any]:
    service = state.get("service_name") or ""
    evidence: dict[str, Any] = {}

    try:
        evidence["error_lines"] = loki_tool.error_lines(service)
    except Exception as exc:  # noqa: BLE001 - recorded as evidence, not fatal
        evidence["logs_error"] = str(exc)

    try:
        evidence["error_rate"] = prometheus_tool.error_rate(service)
        evidence["p95_latency"] = prometheus_tool.p95_latency_seconds(service)
    except Exception as exc:  # noqa: BLE001
        evidence["metrics_error"] = str(exc)

    deployment_version = None
    try:
        deployment_version = get_deployment_image_tag(service, APP_NAMESPACE)
    except Exception as exc:  # noqa: BLE001
        evidence["deployment_lookup_error"] = str(exc)

    evidence["crash_loop"] = "CrashLoopBackOff" in str(evidence.get("error_lines", ""))

    # Captured now (the failing state) so Validation can confirm a measurable
    # improvement, not just an absolute threshold (FR-19/20).
    baseline = {
        "error_rate": evidence.get("error_rate"),
        "p95_latency": evidence.get("p95_latency"),
    }

    return {"evidence": evidence, "deployment_version": deployment_version, "baseline": baseline}
