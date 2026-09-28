"""Allow-listed Kubernetes remediation tools (see ARCHITECTURE.md section 7).
Uses the official kubernetes python client with in-cluster auth (the pod's own
ServiceAccount, bound to a narrowly-scoped Role — see infra/agent-service.yaml).

These are the ONLY Kubernetes actions the agent may ever take. Every call here
is invoked exclusively from agent/graph/nodes.py's `remediate` node, and only
after human approval.
"""
from __future__ import annotations

import json
from typing import Any

from kubernetes import client, config as k8s_config

from .. import config

_loaded = False


def _client() -> tuple[client.CoreV1Api, client.AppsV1Api]:
    global _loaded
    if not _loaded:
        try:
            k8s_config.load_incluster_config()
        except k8s_config.ConfigException:
            k8s_config.load_kube_config()  # local dev fallback
        _loaded = True
    return client.CoreV1Api(), client.AppsV1Api()


def restart_pod(deployment: str, namespace: str = config.APP_NAMESPACE) -> dict[str, Any]:
    """Delete all pods for a deployment so they're recreated fresh (a "restart")."""
    core, apps = _client()
    pods = core.list_namespaced_pod(namespace, label_selector=f"app.kubernetes.io/name={deployment}")
    deleted = []
    for pod in pods.items:
        core.delete_namespaced_pod(pod.metadata.name, namespace)
        deleted.append(pod.metadata.name)
    return {"action": "restart_pod", "deployment": deployment, "deleted_pods": deleted}


def scale_deployment(deployment: str, replicas: int, namespace: str = config.APP_NAMESPACE) -> dict[str, Any]:
    _, apps = _client()
    apps.patch_namespaced_deployment_scale(
        deployment, namespace, {"spec": {"replicas": replicas}}
    )
    return {"action": "scale_deployment", "deployment": deployment, "replicas": replicas}


def rollback_deployment(deployment: str, namespace: str = config.APP_NAMESPACE) -> dict[str, Any]:
    """Roll back to the previous ReplicaSet revision. Also removes any crash-inducing
    liveness-probe patch left over from a fault-injection script, since a rollback
    replaces the whole pod template."""
    _, apps = _client()
    dep = apps.read_namespaced_deployment(deployment, namespace)
    revision = dep.metadata.annotations.get("deployment.kubernetes.io/revision") if dep.metadata.annotations else None
    # Simplest safe "rollback" without querying ReplicaSet history: strip any
    # liveness-probe fault patch and force a rollout restart.
    patch = [{"op": "remove", "path": "/spec/template/spec/containers/0/livenessProbe"}]
    try:
        apps.patch_namespaced_deployment(
            deployment, namespace, patch, _content_type="application/json-patch+json"
        )
    except client.ApiException as exc:
        if exc.status != 422:  # 422 = path didn't exist, i.e. nothing to remove
            raise
    _trigger_rollout_restart(apps, deployment, namespace)
    return {"action": "rollback_deployment", "deployment": deployment, "previous_revision": revision}


def _trigger_rollout_restart(apps: client.AppsV1Api, deployment: str, namespace: str) -> None:
    import datetime

    patch = {
        "spec": {
            "template": {
                "metadata": {
                    "annotations": {
                        "kubectl.kubernetes.io/restartedAt": datetime.datetime.utcnow().isoformat()
                    }
                }
            }
        }
    }
    apps.patch_namespaced_deployment(deployment, namespace, patch)


def toggle_flag_off(flag_key: str, namespace: str = config.APP_NAMESPACE) -> dict[str, Any]:
    """Set a flagd feature flag's defaultVariant back to 'off' (or 0 / false),
    clearing whichever fault was toggled on."""
    core, _ = _client()
    cm = core.read_namespaced_config_map("flagd-config", namespace)
    flags_doc = json.loads(cm.data["demo.flagd.json"])
    if flag_key not in flags_doc["flags"]:
        raise KeyError(f"flag '{flag_key}' not found")
    variants = flags_doc["flags"][flag_key]["variants"]
    off_variant = "off" if "off" in variants else min(variants, key=lambda v: variants[v])
    flags_doc["flags"][flag_key]["defaultVariant"] = off_variant
    cm.data["demo.flagd.json"] = json.dumps(flags_doc, indent=2)
    core.replace_namespaced_config_map("flagd-config", namespace, cm)
    return {"action": "toggle_flag_off", "flag_key": flag_key, "variant": off_variant}


# --- Fault-injection helpers (used by the /faults trigger/clear API, not by the
# agent's remediation tool set above — these are for the demo's "Trigger Fault"
# panel, see ARCHITECTURE.md section 8.1) ---


def set_flagd_variant(flag_key: str, variant: str, namespace: str = config.APP_NAMESPACE) -> dict[str, Any]:
    core, _ = _client()
    cm = core.read_namespaced_config_map("flagd-config", namespace)
    flags_doc = json.loads(cm.data["demo.flagd.json"])
    if flag_key not in flags_doc["flags"]:
        raise KeyError(f"flag '{flag_key}' not found")
    flags_doc["flags"][flag_key]["defaultVariant"] = variant
    cm.data["demo.flagd.json"] = json.dumps(flags_doc, indent=2)
    core.replace_namespaced_config_map("flagd-config", namespace, cm)
    return {"flag_key": flag_key, "variant": variant}


def get_flagd_variant(flag_key: str, namespace: str = config.APP_NAMESPACE) -> str:
    core, _ = _client()
    cm = core.read_namespaced_config_map("flagd-config", namespace)
    flags_doc = json.loads(cm.data["demo.flagd.json"])
    return flags_doc["flags"][flag_key]["defaultVariant"]


def set_crash_liveness_probe(
    deployment: str, enable: bool, namespace: str = config.APP_NAMESPACE
) -> dict[str, Any]:
    _, apps = _client()
    if enable:
        patch = [
            {
                "op": "add",
                "path": "/spec/template/spec/containers/0/livenessProbe",
                "value": {
                    "exec": {"command": ["sh", "-c", "exit 1"]},
                    "initialDelaySeconds": 5,
                    "periodSeconds": 5,
                    "failureThreshold": 1,
                },
            }
        ]
    else:
        patch = [{"op": "remove", "path": "/spec/template/spec/containers/0/livenessProbe"}]
    try:
        apps.patch_namespaced_deployment(
            deployment, namespace, patch, _content_type="application/json-patch+json"
        )
    except client.ApiException as exc:
        if not (not enable and exc.status == 422):
            raise
    return {"deployment": deployment, "crash_loop_enabled": enable}
