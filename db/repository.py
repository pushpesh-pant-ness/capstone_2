"""The only module allowed to run SQL (NFR-14). Routers and the agent call these
functions; nobody else writes raw queries. Uses asyncpg + a module-level pool
created at FastAPI startup (see api/main.py).
"""
from __future__ import annotations

import json
import os
from typing import Any, Optional
from uuid import UUID

import asyncpg

_REDACT_KEYS = {"token", "password", "secret", "authorization", "api_key", "kubeconfig"}
_JSON_COLUMNS = {"evidence", "baseline", "remediation_plan", "validation_result", "payload"}

_pool: Optional[asyncpg.Pool] = None


def _parse_row(row: asyncpg.Record) -> dict[str, Any]:
    """asyncpg returns JSONB columns as raw text by default — decode the known
    JSON columns here so every caller gets structured Python data, not a string."""
    result = dict(row)
    for key in _JSON_COLUMNS & result.keys():
        value = result[key]
        if isinstance(value, str) and value:
            result[key] = json.loads(value)
    return result


async def init_pool() -> None:
    global _pool
    _pool = await asyncpg.create_pool(
        dsn=os.environ.get("DATABASE_URL", "postgresql://incident_agent:incident_agent_dev_password@localhost:5432/incident_agent"),
        min_size=1,
        max_size=10,
    )


async def close_pool() -> None:
    if _pool is not None:
        await _pool.close()


def _pool_or_raise() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("DB pool not initialized — call init_pool() at startup")
    return _pool


def redact(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    """Recursively blank out obviously-secret keys before anything is persisted
    to audit_log (NFR-3, SRS §6.2 'secrets redacted')."""
    if payload is None:
        return None

    def _walk(value: Any) -> Any:
        if isinstance(value, dict):
            return {
                k: ("***redacted***" if k.lower() in _REDACT_KEYS else _walk(v))
                for k, v in value.items()
            }
        if isinstance(value, list):
            return [_walk(v) for v in value]
        return value

    return _walk(payload)


# --- Incidents ---------------------------------------------------------------

async def create_incident(
    alert_fingerprint: str,
    title: str,
    description: str | None,
    service_name: str | None,
) -> UUID:
    query = """
        INSERT INTO incidents (alert_fingerprint, title, description, service_name, status)
        VALUES ($1, $2, $3, $4, 'detected')
        ON CONFLICT (alert_fingerprint) WHERE status NOT IN ('resolved', 'escalated')
        DO UPDATE SET title = EXCLUDED.title
        RETURNING incident_id
    """
    async with _pool_or_raise().acquire() as conn:
        row = await conn.fetchrow(query, alert_fingerprint, title, description, service_name)
        return row["incident_id"]


async def get_incident(incident_id: UUID) -> dict | None:
    async with _pool_or_raise().acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM incidents WHERE incident_id = $1", incident_id)
        return _parse_row(row) if row else None


async def list_incidents(status: str | None = None, limit: int = 50) -> list[dict]:
    async with _pool_or_raise().acquire() as conn:
        if status:
            rows = await conn.fetch(
                "SELECT * FROM incidents WHERE status = $1 ORDER BY detected_at DESC LIMIT $2",
                status, limit,
            )
        else:
            rows = await conn.fetch(
                "SELECT * FROM incidents ORDER BY detected_at DESC LIMIT $1", limit
            )
        return [_parse_row(r) for r in rows]


async def list_resolved_incidents(limit: int = 200) -> list[dict]:
    """Feeds the heuristic historical-similarity scorer (FR-8) — no embeddings,
    just title/service/severity overlap over past resolved incidents."""
    async with _pool_or_raise().acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT incident_id, title, service_name, severity, root_cause_summary,
                   remediation_plan, validation_result
            FROM incidents
            WHERE status IN ('resolved', 'escalated')
            ORDER BY resolved_at DESC NULLS LAST
            LIMIT $1
            """,
            limit,
        )
        return [_parse_row(r) for r in rows]


async def update_incident(incident_id: UUID, **fields: Any) -> None:
    if not fields:
        return
    json_fields = {"evidence", "baseline", "remediation_plan", "validation_result"}
    values: list[Any] = []
    set_parts = []
    for i, (key, value) in enumerate(fields.items(), start=2):
        if key in json_fields and value is not None and not isinstance(value, str):
            value = json.dumps(value)
        set_parts.append(f"{key} = ${i}")
        values.append(value)
    query = f"UPDATE incidents SET {', '.join(set_parts)} WHERE incident_id = $1"
    async with _pool_or_raise().acquire() as conn:
        await conn.execute(query, incident_id, *values)


async def record_approval(incident_id: UUID, approved_by: str) -> None:
    await update_incident(
        incident_id, status="approved", approved_by=approved_by,
    )
    async with _pool_or_raise().acquire() as conn:
        await conn.execute(
            "UPDATE incidents SET approved_at = now() WHERE incident_id = $1", incident_id
        )


async def record_rejection(incident_id: UUID, rejected_by: str, reason: str | None) -> None:
    await update_incident(
        incident_id, status="escalated", approved_by=rejected_by, rejection_reason=reason,
    )


async def mark_resolution(incident_id: UUID, status: str, validation_result: dict) -> None:
    await update_incident(incident_id, status=status, validation_result=validation_result)
    async with _pool_or_raise().acquire() as conn:
        await conn.execute(
            "UPDATE incidents SET resolved_at = now() WHERE incident_id = $1", incident_id
        )


# --- Audit log (append-only, NFR-13 — no update/delete API) ------------------

async def log_audit_event(
    incident_id: UUID, actor: str, action_type: str, payload: dict | None = None
) -> None:
    async with _pool_or_raise().acquire() as conn:
        await conn.execute(
            """
            INSERT INTO audit_log (incident_id, actor, action_type, payload)
            VALUES ($1, $2, $3, $4)
            """,
            incident_id, actor, action_type,
            json.dumps(redact(payload)) if payload is not None else None,
        )


async def list_audit_log(incident_id: UUID) -> list[dict]:
    async with _pool_or_raise().acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM audit_log WHERE incident_id = $1 ORDER BY created_at", incident_id
        )
        return [_parse_row(r) for r in rows]
