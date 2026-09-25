"""Historical retrieval node (FR-8): heuristic similarity scoring over past
resolved incidents (title/service/severity overlap) — no embeddings, that is
Phase 2 (pgvector, SRS §10.C).

Reads candidates via `historical_candidates` already placed on the state by the
caller (api/pipeline.py) — this keeps agent/ free of any db/ import (NFR-14).
"""
from __future__ import annotations

from typing import Any

from .. import heuristics
from ..state import AgentState


async def historical(state: AgentState) -> dict[str, Any]:
    candidates = state.get("historical_candidates", [])  # type: ignore[typeddict-item]
    similar = heuristics.score_similar_incidents(
        title=state.get("title", ""),
        service_name=state.get("service_name"),
        severity=state.get("severity"),
        candidates=candidates,
    )
    return {"similar_incidents": similar}
