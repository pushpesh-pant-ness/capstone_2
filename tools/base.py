"""Common adapter interface (NFR-8). Every external system — LLM, Loki,
Prometheus, each remediation target — is accessed only through a small
interface owned by the calling layer. Concrete implementations are swapped by
pointing config at a new class, never by editing the graph/routers/other callers.
"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Any


class BaseTool(ABC):
    """Read-only or write adapter to one external system."""

    name: str

    @abstractmethod
    def call(self, **kwargs: Any) -> Any:
        ...


class ToolCallError(RuntimeError):
    """Raised after retries are exhausted (NFR-7)."""


def call_with_retry(fn, *args: Any, max_attempts: int = 2, backoff_seconds: float = 1.0, **kwargs: Any) -> Any:
    """Bounded retry with backoff (NFR-7: max 2 attempts) before the caller
    escalates to a human. Attempt count includes the first try."""
    last_exc: Exception | None = None
    for attempt in range(max_attempts):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001 - deliberately broad, we re-raise below
            last_exc = exc
            if attempt < max_attempts - 1:
                time.sleep(backoff_seconds * (attempt + 1))
    raise ToolCallError(f"{fn.__name__} failed after {max_attempts} attempts: {last_exc}") from last_exc


class BaseRemediationTool(BaseTool):
    """Common interface across K8s/AWS/GitHub remediation adapters. Every
    concrete action supports `dry_run` (NFR-5, FR-17) and is re-validated
    against tools/allowlist.yaml by the caller (FR-15) — this class does not
    trust its own callers either.
    """

    target: str  # e.g. "kubernetes"

    @abstractmethod
    def call(self, action: str, dry_run: bool = False, **kwargs: Any) -> dict[str, Any]:
        ...
