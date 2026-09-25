#!/usr/bin/env python
"""Seeds 3-5 synthetic historical (resolved) incidents so FR-8's heuristic
historical-similarity retrieval has data to match against on day one
(TASKS.md §2.2)."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import db.repository as repo

SEED_INCIDENTS = [
    {
        "alert_fingerprint": "seed-1",
        "title": "HighHttpErrorRate",
        "description": "Payment service returning 5xx after deploy",
        "service_name": "payment",
        "severity": "P1",
        "root_cause_summary": "Payment service failing all charge requests after a bad config deploy.",
        "confidence_score": 0.8,
        "remediation_plan": [{"target": "kubernetes", "name": "rollback_deployment", "params": {"deployment": "payment"}, "risk": "medium"}],
        "validation_result": {"recovered": True},
    },
    {
        "alert_fingerprint": "seed-2",
        "title": "HighLatencyP95",
        "description": "Ad service p95 latency spike under load",
        "service_name": "ad",
        "severity": "P2",
        "root_cause_summary": "Ad service under-provisioned for current traffic; high CPU.",
        "confidence_score": 0.65,
        "remediation_plan": [{"target": "kubernetes", "name": "scale_deployment", "params": {"deployment": "ad", "replicas": 3}, "risk": "low_medium"}],
        "validation_result": {"recovered": True},
    },
    {
        "alert_fingerprint": "seed-3",
        "title": "PodCrashLooping",
        "description": "Recommendation service crash-looping after deploy",
        "service_name": "recommendation",
        "severity": "P1",
        "root_cause_summary": "Recommendation container crash-looping due to failing liveness probe after deploy.",
        "confidence_score": 0.75,
        "remediation_plan": [{"target": "kubernetes", "name": "restart_pod", "params": {"deployment": "recommendation"}, "risk": "low"}],
        "validation_result": {"recovered": True},
    },
    {
        "alert_fingerprint": "seed-4",
        "title": "HighHttpErrorRate",
        "description": "Product catalog failing lookups for a specific product",
        "service_name": "product-catalog",
        "severity": "P3",
        "root_cause_summary": "Product catalog service returning errors for a single malformed product ID.",
        "confidence_score": 0.5,
        "remediation_plan": [{"target": "kubernetes", "name": "restart_pod", "params": {"deployment": "product-catalog"}, "risk": "low"}],
        "validation_result": {"recovered": True},
    },
]


async def main() -> None:
    await repo.init_pool()
    try:
        for seed in SEED_INCIDENTS:
            incident_id = await repo.create_incident(
                alert_fingerprint=seed["alert_fingerprint"],
                title=seed["title"],
                description=seed["description"],
                service_name=seed["service_name"],
            )
            await repo.update_incident(
                incident_id,
                severity=seed["severity"],
                root_cause_summary=seed["root_cause_summary"],
                confidence_score=seed["confidence_score"],
                remediation_plan=seed["remediation_plan"],
            )
            await repo.mark_resolution(incident_id, "resolved", seed["validation_result"])
            print(f"Seeded incident {incident_id} ({seed['title']} / {seed['service_name']})")
    finally:
        await repo.close_pool()


if __name__ == "__main__":
    asyncio.run(main())
