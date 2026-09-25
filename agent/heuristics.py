"""Deterministic rule-based fallback for RCA/Planning (used when Bedrock is
unavailable, NFR-6) plus the historical similarity scorer (FR-8 — title/service/
severity overlap, no embeddings needed for the MVP; pgvector is Phase 2).
"""
from __future__ import annotations

from typing import Any

# --- Severity (FR-7) ----------------------------------------------------------

def rule_based_severity(evidence: dict[str, Any]) -> tuple[str, str]:
    error_rate = evidence.get("error_rate", 0.0) or 0.0
    p95_latency = evidence.get("p95_latency", 0.0) or 0.0
    crash_loop = bool(evidence.get("crash_loop"))

    if crash_loop or error_rate >= 0.5:
        return "P1", f"Crash-loop or majority of requests failing (error_rate={error_rate:.2f})"
    if error_rate >= 0.1 or p95_latency >= 5.0:
        return "P2", f"Elevated error rate ({error_rate:.2f}) or high p95 latency ({p95_latency:.1f}s)"
    if error_rate >= 0.02 or p95_latency >= 2.0:
        return "P3", f"Mild error rate ({error_rate:.2f}) or latency increase ({p95_latency:.1f}s)"
    return "P4", "No significant deviation detected in error rate or latency"


# --- RCA (FR-9) ----------------------------------------------------------------

def rule_based_rca(evidence: dict[str, Any], deployment_version: str | None) -> tuple[str, float]:
    error_lines = evidence.get("error_lines") or []
    recent_deploy = bool(deployment_version)
    crash_loop = bool(evidence.get("crash_loop"))
    p95_latency = evidence.get("p95_latency", 0.0) or 0.0
    oom = any("oom" in str(l).lower() or "out of memory" in str(l).lower() for l in error_lines)

    if crash_loop and recent_deploy:
        return (
            f"Pod is crash-looping shortly after deployment {deployment_version}; "
            "most likely a bad config or startup failure introduced by the recent deploy.",
            0.6,
        )
    if oom:
        return "Error logs indicate out-of-memory kills; service is likely under-provisioned.", 0.55
    if p95_latency >= 5.0 and recent_deploy:
        return (
            f"Latency spike correlates with deployment {deployment_version}; "
            "likely a regression or resource saturation introduced by the recent change.",
            0.5,
        )
    if error_lines:
        return f"Errors observed in logs ({len(error_lines)} lines) but no strong deterministic signal matched.", 0.3
    return "No conclusive evidence found by rule-based fallback; defaulting to low-confidence generic hypothesis.", 0.2


# --- Plan (FR-10) --------------------------------------------------------------

def rule_based_plan(root_cause_summary: str, evidence: dict[str, Any], service_name: str | None) -> list[dict[str, Any]]:
    summary = root_cause_summary.lower()
    service = service_name or "unknown-service"

    if "crash-loop" in summary or evidence.get("crash_loop"):
        return [{
            "target": "kubernetes", "name": "restart_pod",
            "params": {"deployment": service}, "risk": "low",
            "expected_effect": "Pod restarts cleanly and stops crash-looping",
        }]
    if "out-of-memory" in summary or "under-provisioned" in summary:
        return [{
            "target": "kubernetes", "name": "scale_deployment",
            "params": {"deployment": service, "replicas": 3}, "risk": "low_medium",
            "expected_effect": "Additional replicas relieve memory/CPU pressure",
        }]
    if "deployment" in summary and ("regression" in summary or "bad config" in summary):
        return [{
            "target": "kubernetes", "name": "rollback_deployment",
            "params": {"deployment": service}, "risk": "medium",
            "expected_effect": "Reverts to the last known-good revision",
        }]
    # Default conservative action when no strong signal matched.
    return [{
        "target": "kubernetes", "name": "restart_pod",
        "params": {"deployment": service}, "risk": "low",
        "expected_effect": "Restart as a safe first attempt; escalate if it does not recover",
    }]


# --- Historical similarity (FR-8) ----------------------------------------------

def _title_overlap(a: str, b: str) -> float:
    words_a = set(a.lower().split())
    words_b = set(b.lower().split())
    if not words_a or not words_b:
        return 0.0
    return len(words_a & words_b) / len(words_a | words_b)


def score_similar_incidents(
    title: str,
    service_name: str | None,
    severity: str | None,
    candidates: list[dict[str, Any]],
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Weighted heuristic score — title word overlap (0.5), same service (0.3),
    same severity (0.2). No embeddings (that's Phase 2 / pgvector)."""
    scored = []
    for candidate in candidates:
        score = 0.0
        score += 0.5 * _title_overlap(title, candidate.get("title", ""))
        if service_name and candidate.get("service_name") == service_name:
            score += 0.3
        if severity and candidate.get("severity") == severity:
            score += 0.2
        if score > 0:
            scored.append({**candidate, "similarity_score": round(score, 3)})
    scored.sort(key=lambda c: c["similarity_score"], reverse=True)
    return scored[:limit]
