"""Fast local checks for agent/heuristics.py — run before every Sync Point
(BUILD_PLAN.md §10): `pytest tests/agent/`."""
from __future__ import annotations

from agent import heuristics


def test_rule_based_severity_crash_loop_is_p1():
    severity, rationale = heuristics.rule_based_severity({"crash_loop": True})
    assert severity == "P1"
    assert rationale


def test_rule_based_severity_no_signal_is_p4():
    severity, _ = heuristics.rule_based_severity({})
    assert severity == "P4"


def test_rule_based_plan_crash_loop_restarts_pod():
    plan = heuristics.rule_based_plan("pod is crash-loop backoff", {"crash_loop": True}, "checkout")
    assert plan[0]["name"] == "restart_pod"
    assert plan[0]["params"]["deployment"] == "checkout"


def test_rule_based_plan_oom_scales_deployment():
    plan = heuristics.rule_based_plan("service is out-of-memory and under-provisioned", {}, "cart")
    assert plan[0]["name"] == "scale_deployment"


def test_score_similar_incidents_weights_service_and_severity():
    candidates = [
        {"incident_id": "1", "title": "High error rate", "service_name": "payment", "severity": "P1"},
        {"incident_id": "2", "title": "Totally unrelated", "service_name": "ad", "severity": "P4"},
    ]
    ranked = heuristics.score_similar_incidents("High error rate spike", "payment", "P1", candidates)
    assert ranked[0]["incident_id"] == "1"
    assert ranked[0]["similarity_score"] > 0
