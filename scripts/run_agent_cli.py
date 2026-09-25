#!/usr/bin/env python
"""Run one incident through the full graph standalone — no FastAPI/UI needed
(NFR-10). Fast iteration during development and a demo-rehearsal safety net
(BUILD_PLAN.md design principle #3: one pipeline, two entry points — this
script calls the exact same api.pipeline.run_investigation used by the webhook
handler).

Usage:
    python scripts/run_agent_cli.py --alert-name HighHttpErrorRate --service payment
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # repo root on sys.path

import db.repository as repo
from agent.state import AgentState
from api.pipeline import run_investigation


async def main(alert_name: str, service_name: str | None) -> None:
    await repo.init_pool()
    try:
        fingerprint = f"cli:{alert_name}:{service_name}"
        incident_id = await repo.create_incident(
            alert_fingerprint=fingerprint,
            title=alert_name,
            description="Triggered via scripts/run_agent_cli.py",
            service_name=service_name,
        )
        initial_state: AgentState = {
            "incident_id": str(incident_id),
            "alert_fingerprint": fingerprint,
            "title": alert_name,
            "service_name": service_name,
            "labels": {"alertname": alert_name, "service_name": service_name or ""},
            "annotations": {},
        }
        await run_investigation(incident_id, initial_state)
        incident = await repo.get_incident(incident_id)
        print(f"Incident {incident_id} -> status={incident['status']}")
        print(f"Severity: {incident['severity']}")
        print(f"Root cause: {incident['root_cause_summary']} (confidence={incident['confidence_score']})")
        print(f"Plan: {incident['remediation_plan']}")
        print(f"Approve with: POST /incidents/{incident_id}/approve")
    finally:
        await repo.close_pool()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--alert-name", required=True)
    parser.add_argument("--service", dest="service_name", default=None)
    args = parser.parse_args()
    asyncio.run(main(args.alert_name, args.service_name))
