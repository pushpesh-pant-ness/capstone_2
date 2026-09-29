"""Fast local checks for agent/guardrail.py's deterministic plan sanity check
(docs/AGENTS.md §4) and the supervisor/rca routing functions built on top of
plain dicts — no LLM, no graph execution needed."""
from __future__ import annotations

from agent.guardrail import check_plan
from agent.nodes.rca import route_after_rca
from agent.nodes.supervisor import find_auto_plan_candidate, route_after_supervisor


# --- guardrail.check_plan ------------------------------------------------------

def test_check_plan_passes_small_in_namespace_plan():
    plan = [{"name": "restart_pod", "params": {"deployment": "checkout"}}]
    assert check_plan(plan, allowed_namespace="default") is None


def test_check_plan_rejects_empty_plan():
    assert check_plan([], allowed_namespace="default") is not None


def test_check_plan_rejects_too_many_actions():
    plan = [{"name": "restart_pod", "params": {}} for _ in range(4)]
    assert check_plan(plan, allowed_namespace="default", max_actions=3) is not None


def test_check_plan_rejects_out_of_namespace_action():
    plan = [{"name": "restart_pod", "params": {"namespace": "kube-system"}}]
    assert check_plan(plan, allowed_namespace="default") is not None


def test_check_plan_rejects_deployment_name_mismatch():
    # Observed live: LLM proposed "payment-service" when the real/given service was "payment".
    plan = [{"name": "restart_pod", "params": {"deployment": "payment-service"}}]
    assert check_plan(plan, allowed_namespace="default", expected_deployment="payment") is not None


def test_check_plan_passes_matching_deployment_name():
    plan = [{"name": "restart_pod", "params": {"deployment": "payment"}}]
    assert check_plan(plan, allowed_namespace="default", expected_deployment="payment") is None


# --- supervisor -----------------------------------------------------------------

def _candidate(**overrides):
    base = {
        "incident_id": "abc",
        "similarity_score": 0.9,
        "remediation_plan": [{"name": "restart_pod", "params": {}}],
        "validation_result": {"recovered": True},
    }
    base.update(overrides)
    return base


def test_find_auto_plan_candidate_requires_p4():
    state = {"severity": "P2", "similar_incidents": [_candidate()]}
    assert find_auto_plan_candidate(state) is None


def test_find_auto_plan_candidate_requires_recovered_outcome():
    state = {"severity": "P4", "similar_incidents": [_candidate(validation_result={"recovered": False})]}
    assert find_auto_plan_candidate(state) is None


def test_find_auto_plan_candidate_requires_high_similarity():
    state = {"severity": "P4", "similar_incidents": [_candidate(similarity_score=0.2)]}
    assert find_auto_plan_candidate(state) is None


def test_find_auto_plan_candidate_rejects_cross_service_match():
    # Observed live: two incidents both titled "PodCrashLooping" (one for
    # "recommendation", one for "payment") reached the similarity threshold
    # on title+severity alone, with no real service match.
    state = {
        "severity": "P4",
        "service_name": "payment",
        "similar_incidents": [_candidate(service_name="recommendation")],
    }
    assert find_auto_plan_candidate(state) is None


def test_find_auto_plan_candidate_matches_and_routes_to_auto_plan():
    state = {"severity": "P4", "similar_incidents": [_candidate()]}
    assert find_auto_plan_candidate(state) is not None
    assert route_after_supervisor(state) == "auto_plan"


def test_route_after_supervisor_defaults_to_rca():
    state = {"severity": "P2", "similar_incidents": []}
    assert route_after_supervisor(state) == "rca"


# --- rca routing ------------------------------------------------------------

def test_route_after_rca_escalates_on_low_confidence():
    assert route_after_rca({"low_confidence": True}) == "escalate"


def test_route_after_rca_plans_otherwise():
    assert route_after_rca({"low_confidence": False}) == "plan"
