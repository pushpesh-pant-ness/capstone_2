"""LogQL query wrapper for the Investigate node (FR-4). Talks to Grafana Loki
over HTTP — no credentials needed for local dev (Loki has no auth by default).
"""
from __future__ import annotations

import os
import time
from typing import Any

import requests

from .base import BaseTool

LOKI_URL = os.environ.get("LOKI_URL", "http://localhost:3100")


class LokiTool(BaseTool):
    name = "loki"

    def call(self, service_name: str, minutes: int = 15, limit: int = 200) -> list[dict[str, Any]]:
        return self.query_range(service_name, minutes=minutes, limit=limit)

    def query_range(self, service_name: str, minutes: int = 15, limit: int = 200) -> list[dict[str, Any]]:
        end = time.time()
        start = end - minutes * 60
        params = {
            "query": f'{{service_name="{service_name}"}}',
            "start": str(int(start * 1e9)),
            "end": str(int(end * 1e9)),
            "limit": str(limit),
            "direction": "backward",
        }
        resp = requests.get(f"{LOKI_URL}/loki/api/v1/query_range", params=params, timeout=10)
        resp.raise_for_status()
        result = resp.json().get("data", {}).get("result", [])
        lines: list[dict[str, Any]] = []
        for stream in result:
            for ts, line in stream.get("values", []):
                lines.append({"timestamp": ts, "line": line, "labels": stream.get("stream", {})})
        return lines

    def error_lines(self, service_name: str, minutes: int = 15) -> list[dict[str, Any]]:
        """Filtered to error/warn — same idea as OTel's SeverityText field
        (DFD.md §4.1) so RCA prompts aren't flooded with noise."""
        lines = self.query_range(service_name, minutes=minutes)
        return [
            l for l in lines
            if any(tag in l["line"].upper() for tag in ("ERROR", "WARN", "EXCEPTION", "FATAL"))
        ]


loki_tool = LokiTool()
