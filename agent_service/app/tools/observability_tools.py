"""Read-only evidence-gathering tools used by the agent's "investigate" node.
All calls are plain HTTP against in-cluster services — no credentials needed
since these backends aren't exposed outside the cluster.
"""
from __future__ import annotations

import time
from typing import Any

import requests

from .. import config


def query_loki(service_name: str, minutes: int = 15, limit: int = 100) -> list[dict[str, Any]]:
    """Fetch recent log lines for a service from Loki."""
    end = time.time()
    start = end - minutes * 60
    params = {
        "query": f'{{service_name="{service_name}"}}',
        "start": str(int(start * 1e9)),
        "end": str(int(end * 1e9)),
        "limit": str(limit),
        "direction": "backward",
    }
    resp = requests.get(f"{config.LOKI_URL}/loki/api/v1/query_range", params=params, timeout=10)
    resp.raise_for_status()
    result = resp.json().get("data", {}).get("result", [])
    lines: list[dict[str, Any]] = []
    for stream in result:
        for ts, line in stream.get("values", []):
            lines.append({"timestamp": ts, "line": line, "labels": stream.get("stream", {})})
    return lines


def query_prometheus_range(promql: str, minutes: int = 15, step: str = "30s") -> dict[str, Any]:
    """Run a PromQL range query against Prometheus."""
    end = time.time()
    start = end - minutes * 60
    params = {"query": promql, "start": start, "end": end, "step": step}
    resp = requests.get(f"{config.PROMETHEUS_URL}/api/v1/query_range", params=params, timeout=10)
    resp.raise_for_status()
    return resp.json().get("data", {})


def query_prometheus_instant(promql: str) -> dict[str, Any]:
    resp = requests.get(
        f"{config.PROMETHEUS_URL}/api/v1/query", params={"query": promql}, timeout=10
    )
    resp.raise_for_status()
    return resp.json().get("data", {})


def query_traces(service_name: str, limit: int = 20) -> list[dict[str, Any]]:
    """Fetch recent traces for a service from Jaeger's query API."""
    resp = requests.get(
        f"{config.JAEGER_URL}/api/traces",
        params={"service": service_name, "limit": limit},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json().get("data", [])
