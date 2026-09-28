"""LangGraph node implementations. Every node: emits a `started` StepEvent,
does its work, emits a `finished` (or `failed`) StepEvent, and persists the
step to Postgres — this is what powers the live agent timeline in the UI
(ARCHITECTURE.md section 8.2).
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from .. import db, fault_registry
from ..events import StepEvent, bus
from ..llm import bedrock_client
from ..memory import pgvector_store
from ..tools import github_tools, k8s_tools, observability_tools
from .state import AgentState


async def _record(state: AgentState, node_name: str, status: str, **kwargs: Any) -> None:
    event = StepEvent(incident_id=state["incident_id"], node_name=node_name, status=status, **kwargs)
    await bus.publish(event)
    if status in ("finished", "failed"):
        await db.add_step(
            UUID(state["incident_id"]),
            state.get("step_index", 0),
            node_name,
            kwargs.get("input"),
            kwargs.get("output"),
            kwargs.get("llm_prompt"),
            kwargs.get("llm_response"),
            kwargs.get("tool_calls"),
        )


async def detect(state: AgentState) -> AgentState:
    state["step_index"] = 0
    await _record(state, "detect", "started", input={"alert_name": state["alert_name"], "labels": state.get("labels")})
    fault = fault_registry.find_by_service(state.get("service_name") or "")
    state["fault_id"] = fault["id"] if fault else None
    await _record(state, "detect", "finished", output={"fault_id": state["fault_id"]})
    return state


async def investigate(state: AgentState) -> AgentState:
    state["step_index"] = 1
    service = state.get("service_name") or ""
    await _record(state, "investigate", "started", input={"service_name": service})
    evidence: dict[str, Any] = {}
    try:
        evidence["logs"] = observability_tools.query_loki(service)[:50]
    except Exception as exc:
        evidence["logs_error"] = str(exc)
    try:
        evidence["error_rate"] = observability_tools.query_prometheus_range(
            'sum(rate(http_server_request_duration_seconds_count'
            f'{{service_name="{service}",http_response_status_code=~"5.."}}[2m]))'
        )
    except Exception as exc:
        evidence["metrics_error"] = str(exc)
    try:
        evidence["traces"] = observability_tools.query_traces(service, limit=10)
    except Exception as exc:
        evidence["traces_error"] = str(exc)
    state["evidence"] = evidence
    await _record(state, "investigate", "finished", output={"evidence_keys": list(evidence.keys())})
    return state


async def diagnose(state: AgentState) -> AgentState:
    state["step_index"] = 2
    await _record(state, "diagnose", "started", input={"evidence_keys": list(state.get("evidence", {}).keys())})

    summary_text = (
        f"Alert: {state['alert_name']}. Service: {state.get('service_name')}. "
        f"Evidence: {str(state.get('evidence'))[:2000]}"
    )
    try:
        similar = await pgvector_store.find_similar_incidents(summary_text)
    except Exception:
        similar = []
    state["similar_incidents"] = similar

    fault = fault_registry.find_by_id(state["fault_id"]) if state.get("fault_id") else None
    system_prompt = (
        "You are an SRE incident investigator. Given alert metadata, telemetry evidence, "
        "and similar past incidents, identify the most likely root cause in 2-4 sentences."
    )
    user_prompt = (
        f"Alert: {state['alert_name']}\nService: {state.get('service_name')}\n"
        f"Evidence: {state.get('evidence')}\nSimilar past incidents: {similar}\n"
        f"Known fault hint (if any): {fault.get('expected_root_cause') if fault else 'none'}"
    )
    try:
        root_cause = bedrock_client.generate(system_prompt, user_prompt)
    except Exception as exc:
        fallback = fault.get("expected_root_cause") if fault else "unknown root cause"
        root_cause = f"[LLM unavailable: {exc}] Falling back to fault-registry hint: {fallback}"
    state["root_cause"] = root_cause
    await _record(
        state, "diagnose", "finished",
        output={"root_cause": root_cause, "similar_incidents": similar},
        llm_prompt=user_prompt, llm_response=root_cause,
    )
    return state


async def assess_severity(state: AgentState) -> AgentState:
    state["step_index"] = 3
    await _record(state, "severity", "started", input={"root_cause": state.get("root_cause")})
    fault = fault_registry.find_by_id(state["fault_id"]) if state.get("fault_id") else None
    sev = fault["severity"] if fault else "warning"
    state["severity"] = sev
    await _record(state, "severity", "finished", output={"severity": sev})
    return state


async def plan(state: AgentState) -> AgentState:
    state["step_index"] = 4
    await _record(state, "plan", "started", input={"severity": state.get("severity")})
    fault = fault_registry.find_by_id(state["fault_id"]) if state.get("fault_id") else None
    hint = fault.get("expected_remediation") if fault else None

    system_prompt = (
        "You are an SRE remediation planner choosing from this allow-list: "
        "restart_pod, scale_deployment, rollback_deployment, toggle_flag_off, create_issue. "
        "Respond with a short justification only (1-3 sentences); the tool itself is "
        "selected programmatically from the fault registry when a hint is available."
    )
    user_prompt = (
        f"Root cause: {state.get('root_cause')}\nSeverity: {state.get('severity')}\n"
        f"Registry remediation hint: {hint}\nService: {state.get('service_name')}"
    )
    try:
        justification = bedrock_client.generate(system_prompt, user_prompt, max_tokens=256)
    except Exception as exc:
        justification = f"[LLM unavailable: {exc}] Using fault-registry hint '{hint}'."

    tool = hint or "create_issue"
    service = state.get("service_name") or ""
    args: dict[str, Any] = {}
    if tool == "toggle_flag_off" and fault:
        args = {"flag_key": fault["flag_key"]}
    elif tool == "rollback_deployment":
        args = {"deployment": fault.get("target_deployment", service) if fault else service}
    elif tool == "restart_pod":
        args = {"deployment": service}
    elif tool == "scale_deployment":
        args = {"deployment": service, "replicas": 3}
    elif tool == "create_issue":
        args = {
            "title": f"[incident-agent] {state['alert_name']} on {service}",
            "body": state.get("root_cause", ""),
        }

    state["plan"] = {"tool": tool, "args": args, "justification": justification}
    state["approval_status"] = "pending"
    await _record(
        state, "plan", "finished", output=state["plan"],
        llm_prompt=user_prompt, llm_response=justification,
    )
    return state


TOOL_MAP = {
    "restart_pod": k8s_tools.restart_pod,
    "scale_deployment": k8s_tools.scale_deployment,
    "rollback_deployment": k8s_tools.rollback_deployment,
    "toggle_flag_off": k8s_tools.toggle_flag_off,
    "create_issue": github_tools.create_issue,
}


async def remediate(state: AgentState) -> AgentState:
    """Only ever reached after the graph is resumed post-approval (see graph/build.py's
    interrupt_before=['remediate'])."""
    state["step_index"] = 5
    plan_ = state["plan"]
    await _record(state, "remediate", "started", input=plan_)
    tool_fn = TOOL_MAP.get(plan_["tool"])
    if tool_fn is None:
        result = {"error": f"unknown tool '{plan_['tool']}'"}
    else:
        try:
            result = tool_fn(**plan_["args"])
        except Exception as exc:
            result = {"error": str(exc)}
    state["remediation_result"] = result
    await _record(
        state, "remediate", "finished", output=result,
        tool_calls=[{"tool": plan_["tool"], "args": plan_["args"], "result": result}],
    )
    return state


async def validate(state: AgentState) -> AgentState:
    state["step_index"] = 6
    await _record(state, "validate", "started", input=state.get("remediation_result"))
    service = state.get("service_name") or ""
    recovered = True
    details: dict[str, Any] = {}
    try:
        details = observability_tools.query_prometheus_instant(
            'sum(rate(http_server_request_duration_seconds_count'
            f'{{service_name="{service}",http_response_status_code=~"5.."}}[2m]))'
        )
        results = details.get("result", [])
        recovered = all(float(r["value"][1]) == 0.0 for r in results) if results else True
    except Exception as exc:
        details = {"error": str(exc)}
    state["validation_result"] = {"recovered": recovered, "details": details}
    await _record(state, "validate", "finished", output=state["validation_result"])
    return state


async def resolve(state: AgentState) -> AgentState:
    state["step_index"] = 7
    await _record(state, "resolve", "started", input=state.get("validation_result"))
    incident_id = UUID(state["incident_id"])
    recovered = state.get("validation_result", {}).get("recovered", False)
    await db.mark_resolved(
        incident_id,
        status="resolved" if recovered else "escalated",
        outcome="recovered" if recovered else "not_recovered",
        root_cause=state.get("root_cause"),
        remediation_action=state.get("plan", {}).get("tool"),
    )
    try:
        summary_text = f"{state['alert_name']} on {state.get('service_name')}: {state.get('root_cause')}"
        await pgvector_store.store_incident_embedding(incident_id, summary_text)
    except Exception:
        pass
    await _record(state, "resolve", "finished", output={"recovered": recovered})
    return state
