"""Kubernetes remediation adapter — the only write-capable tool in the MVP
allow-list (SRS §7): restart_pod, rollback_deployment, scale_deployment.

FR-15: re-validates every action against tools/allowlist.yaml itself — does not
trust the Planning node's filtering alone.
FR-17: every action supports dry_run.
FR-18: runs only against the configured kubeconfig context, never inferred.
NFR-7: bounded retry with backoff on failure (max 2 attempts).
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from kubernetes import client, config as k8s_config

from .base import BaseRemediationTool, call_with_retry

ALLOWLIST_PATH = Path(__file__).parent / "allowlist.yaml"
KUBECONFIG_CONTEXT = os.environ.get("KUBECONFIG_CONTEXT")  # e.g. "kind-incident-agent" — never inferred


def _load_allowed_actions() -> set[str]:
    with open(ALLOWLIST_PATH, "r", encoding="utf-8") as f:
        doc = yaml.safe_load(f)
    return {t["name"] for t in doc["tools"] if t["target"] == "kubernetes"}


class K8sTool(BaseRemediationTool):
    name = "k8s"
    target = "kubernetes"

    def __init__(self) -> None:
        self._loaded = False
        self._core: client.CoreV1Api | None = None
        self._apps: client.AppsV1Api | None = None

    def _clients(self) -> tuple[client.CoreV1Api, client.AppsV1Api]:
        if not self._loaded:
            if KUBECONFIG_CONTEXT:
                k8s_config.load_kube_config(context=KUBECONFIG_CONTEXT)
            else:
                try:
                    k8s_config.load_incluster_config()
                except k8s_config.ConfigException:
                    k8s_config.load_kube_config()
            self._core = client.CoreV1Api()
            self._apps = client.AppsV1Api()
            self._loaded = True
        assert self._core is not None and self._apps is not None
        return self._core, self._apps

    def call(self, action: str, dry_run: bool = False, **kwargs: Any) -> dict[str, Any]:
        if action not in _load_allowed_actions():
            raise ValueError(f"action '{action}' is not on tools/allowlist.yaml — refusing to run it")
        handler = getattr(self, action, None)
        if handler is None:
            raise ValueError(f"action '{action}' has no implementation")

        def _handler_with_reload(*args: Any, **kw: Any) -> dict[str, Any]:
            try:
                return handler(*args, **kw)
            except Exception:
                # The cached client can outlive the cluster endpoint it was built
                # against (e.g. a kind cluster's host-mapped API server port
                # changes after a Docker Desktop restart) — drop it so the next
                # attempt (this retry, or a later incident) reloads kubeconfig
                # fresh instead of failing against a dead endpoint forever.
                self._loaded = False
                raise

        return call_with_retry(_handler_with_reload, dry_run=dry_run, **kwargs)

    def _deployment_selector(self, deployment: str, namespace: str) -> str:
        """Build a label selector from the Deployment's own spec.selector.matchLabels —
        never assume an `app=` convention, since not every manifest uses it (e.g. the
        opentelemetry-demo chart labels with app.kubernetes.io/name instead)."""
        _, apps = self._clients()
        dep = apps.read_namespaced_deployment(deployment, namespace)
        match_labels = dep.spec.selector.match_labels or {}
        return ",".join(f"{k}={v}" for k, v in match_labels.items())

    def restart_pod(self, deployment: str, namespace: str, dry_run: bool = False) -> dict[str, Any]:
        core, _ = self._clients()
        selector = self._deployment_selector(deployment, namespace)
        pods = core.list_namespaced_pod(namespace, label_selector=selector)
        names = [p.metadata.name for p in pods.items]
        if dry_run:
            return {"action": "restart_pod", "deployment": deployment, "would_delete_pods": names, "dry_run": True}
        deleted = []
        for name in names:
            core.delete_namespaced_pod(name, namespace)
            deleted.append(name)
        return {"action": "restart_pod", "deployment": deployment, "deleted_pods": deleted, "dry_run": False}

    def rollback_deployment(self, deployment: str, namespace: str, dry_run: bool = False) -> dict[str, Any]:
        _, apps = self._clients()
        dep = apps.read_namespaced_deployment(deployment, namespace)
        current_revision = (dep.metadata.annotations or {}).get("deployment.kubernetes.io/revision")
        if dry_run:
            return {
                "action": "rollback_deployment", "deployment": deployment,
                "current_revision": current_revision, "dry_run": True,
            }
        selector = self._deployment_selector(deployment, namespace)
        replica_sets = apps.list_namespaced_replica_set(
            namespace, label_selector=selector
        ).items
        candidates = sorted(
            (rs for rs in replica_sets if rs.metadata.annotations
             and rs.metadata.annotations.get("deployment.kubernetes.io/revision") != current_revision),
            key=lambda rs: int(rs.metadata.annotations["deployment.kubernetes.io/revision"]),
        )
        if not candidates:
            raise RuntimeError(f"no previous revision found for deployment '{deployment}'")
        previous = candidates[-1]
        # NOTE: .to_dict() yields Python-side snake_case attribute names, which
        # the API server's strategic-merge-patch rejects (it expects the wire
        # format's camelCase, e.g. containerPort not container_port). Use the
        # client's own serializer, which applies each model's attribute_map.
        core, _ = self._clients()
        template_body = core.api_client.sanitize_for_serialization(previous.spec.template)
        apps.patch_namespaced_deployment(
            deployment, namespace,
            {"spec": {"template": template_body}},
        )
        return {
            "action": "rollback_deployment", "deployment": deployment,
            "rolled_back_from": current_revision,
            "rolled_back_to": previous.metadata.annotations["deployment.kubernetes.io/revision"],
            "dry_run": False,
        }

    def scale_deployment(self, deployment: str, replicas: int, namespace: str, dry_run: bool = False) -> dict[str, Any]:
        _, apps = self._clients()
        current = apps.read_namespaced_deployment_scale(deployment, namespace)
        if dry_run:
            return {
                "action": "scale_deployment", "deployment": deployment,
                "current_replicas": current.spec.replicas, "target_replicas": replicas, "dry_run": True,
            }
        apps.patch_namespaced_deployment_scale(deployment, namespace, {"spec": {"replicas": replicas}})
        return {
            "action": "scale_deployment", "deployment": deployment,
            "previous_replicas": current.spec.replicas, "replicas": replicas, "dry_run": False,
        }


k8s_tool = K8sTool()


def get_deployment_image_tag(deployment: str, namespace: str) -> str | None:
    """Read-only lookup of the running container image (last deployed
    version/commit) for the Investigate node (FR-5). Not part of the
    remediation allow-list — this never mutates anything."""
    _, apps = k8s_tool._clients()  # noqa: SLF001 - shares the same cached client
    try:
        dep = apps.read_namespaced_deployment(deployment, namespace)
    except Exception:
        k8s_tool._loaded = False  # noqa: SLF001 - see call()'s _handler_with_reload
        raise
    containers = dep.spec.template.spec.containers
    return containers[0].image if containers else None


def is_crash_looping(deployment: str, namespace: str) -> bool:
    """Read-only K8s health check for the Validation loop (FR-19: 'Poll
    Prometheus + K8s health checks', not Prometheus error-rate alone). Returns
    True if any pod backing this deployment is currently waiting in
    CrashLoopBackOff or not ready."""
    core, _ = k8s_tool._clients()  # noqa: SLF001 - shares the same cached client
    try:
        selector = k8s_tool._deployment_selector(deployment, namespace)  # noqa: SLF001
        pods = core.list_namespaced_pod(namespace, label_selector=selector)
    except Exception:
        k8s_tool._loaded = False  # noqa: SLF001 - see call()'s _handler_with_reload
        raise
    for pod in pods.items:
        for status in pod.status.container_statuses or []:
            waiting = status.state.waiting
            if waiting and waiting.reason == "CrashLoopBackOff":
                return True
            if not status.ready and status.restart_count > 0:
                return True
    return False
