"""GitHub remediation tool — creates an issue documenting the incident (and,
optionally, a suggested fix). Requires GITHUB_TOKEN + GITHUB_REPO env vars
(see infra/agent-service.yaml); raises clearly if not configured rather than
silently no-op'ing.
"""
from __future__ import annotations

from typing import Any

import requests

from .. import config


def create_issue(title: str, body: str, labels: list[str] | None = None) -> dict[str, Any]:
    if not config.GITHUB_TOKEN or not config.GITHUB_REPO:
        raise RuntimeError(
            "GITHUB_TOKEN / GITHUB_REPO not configured — set them as a k8s Secret "
            "to enable the GitHub remediation tool."
        )
    resp = requests.post(
        f"https://api.github.com/repos/{config.GITHUB_REPO}/issues",
        headers={
            "Authorization": f"Bearer {config.GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json",
        },
        json={"title": title, "body": body, "labels": labels or ["incident-agent"]},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    return {"action": "create_issue", "issue_url": data["html_url"], "issue_number": data["number"]}
