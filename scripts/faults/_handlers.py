"""Low-level fault handlers for scripts/faults/inject.py — a standalone CLI for
manually triggering/clearing incident scenarios against the monitored app
(DFD.md confirms open-telemetry-demo + flagd). Independent of tools/k8s_tool.py,
which only implements the remediation allow-list (SRS §7), not fault injection.

Everything shells out to `kubectl` deliberately so the exact same command a
human would run is what this script runs.
"""
from __future__ import annotations

import json
import subprocess

OTEL_DEMO_NAMESPACE = "otel-demo"
FLAGD_CONFIGMAP = "flagd-config"
FLAGD_CONFIGMAP_KEY = "demo.flagd.json"


def _kubectl(*args: str, input_text: str | None = None) -> str:
    result = subprocess.run(
        ["kubectl", *args],
        input=input_text,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"kubectl {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def set_flagd_variant(flag_key: str, variant: str, namespace: str = OTEL_DEMO_NAMESPACE) -> None:
    """Set a flagd flag's defaultVariant. flagd watches the mounted configmap file
    and picks up the change automatically (fsnotify) — no pod restart needed."""
    raw = _kubectl("get", "configmap", FLAGD_CONFIGMAP, "-n", namespace, "-o", "json")
    cm = json.loads(raw)
    flags_doc = json.loads(cm["data"][FLAGD_CONFIGMAP_KEY])

    if flag_key not in flags_doc["flags"]:
        raise KeyError(f"flag '{flag_key}' not found in {FLAGD_CONFIGMAP_KEY}")
    flags_doc["flags"][flag_key]["defaultVariant"] = variant
    cm["data"][FLAGD_CONFIGMAP_KEY] = json.dumps(flags_doc, indent=2)

    _kubectl("apply", "-f", "-", input_text=json.dumps(cm))


def get_flagd_variant(flag_key: str, namespace: str = OTEL_DEMO_NAMESPACE) -> str:
    raw = _kubectl("get", "configmap", FLAGD_CONFIGMAP, "-n", namespace, "-o", "json")
    cm = json.loads(raw)
    flags_doc = json.loads(cm["data"][FLAGD_CONFIGMAP_KEY])
    return flags_doc["flags"][flag_key]["defaultVariant"]


def set_crash_liveness_probe(deployment: str, enable: bool, namespace: str = OTEL_DEMO_NAMESPACE) -> None:
    """Toggle a failing liveness probe on a Deployment's first container to induce
    a real CrashLoopBackOff (container restart count actually increments, which is
    what the PodCrashLooping alert rule watches)."""
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
        patch = [
            {"op": "remove", "path": "/spec/template/spec/containers/0/livenessProbe"}
        ]
    try:
        _kubectl(
            "patch",
            "deployment",
            deployment,
            "-n",
            namespace,
            "--type=json",
            "-p",
            json.dumps(patch),
        )
    except RuntimeError as exc:
        if not enable and "does not exist" in str(exc):
            return  # already cleared
        raise
