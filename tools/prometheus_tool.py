"""PromQL query wrapper for error-rate/latency/resource metrics (FR-4, used by
Investigate + Validation)."""
from __future__ import annotations

import os
import time
from typing import Any

import requests

from .base import BaseTool

PROMETHEUS_URL = os.environ.get("PROMETHEUS_URL", "http://localhost:9090")


class PrometheusTool(BaseTool):
    name = "prometheus"

    def call(self, promql: str) -> dict[str, Any]:
        return self.query_instant(promql)

    def query_instant(self, promql: str) -> dict[str, Any]:
        resp = requests.get(f"{PROMETHEUS_URL}/api/v1/query", params={"query": promql}, timeout=10)
        resp.raise_for_status()
        return resp.json().get("data", {})

    def query_range(self, promql: str, minutes: int = 15, step: str = "30s") -> dict[str, Any]:
        end = time.time()
        start = end - minutes * 60
        params = {"query": promql, "start": start, "end": end, "step": step}
        resp = requests.get(f"{PROMETHEUS_URL}/api/v1/query_range", params=params, timeout=10)
        resp.raise_for_status()
        return resp.json().get("data", {})

    def error_rate(self, service_name: str, window: str = "5m") -> float:
        promql = (
            f'sum(rate(http_requests_total{{service="{service_name}",status=~"5.."}}[{window}])) '
            f'/ sum(rate(http_requests_total{{service="{service_name}"}}[{window}]))'
        )
        data = self.query_instant(promql)
        results = data.get("result", [])
        return float(results[0]["value"][1]) if results else 0.0

    def p95_latency_seconds(self, service_name: str, window: str = "5m") -> float:
        promql = (
            f'histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket'
            f'{{service="{service_name}"}}[{window}])) by (le))'
        )
        data = self.query_instant(promql)
        results = data.get("result", [])
        return float(results[0]["value"][1]) if results else 0.0


prometheus_tool = PrometheusTool()
