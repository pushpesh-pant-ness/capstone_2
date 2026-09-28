"""Loads scripts/faults/registry.yaml (mounted into this pod via ConfigMap —
see infra/agent-service.yaml) so the agent can look up the expected root cause /
remediation hint for a recognized fault, and so GET /faults can serve the list
that drives the UI's "Trigger Fault" panel."""
from __future__ import annotations

from functools import lru_cache

import yaml

from . import config


@lru_cache(maxsize=1)
def load_registry() -> list[dict]:
    with open(config.FAULT_REGISTRY_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)["faults"]


def find_by_service(service_name: str) -> dict | None:
    for fault in load_registry():
        if fault.get("target_service") == service_name:
            return fault
    return None


def find_by_id(fault_id: str) -> dict | None:
    for fault in load_registry():
        if fault["id"] == fault_id:
            return fault
    return None
