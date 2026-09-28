"""Async Postgres access layer (asyncpg) for the incidents / incident_steps
tables defined in infra/postgres.yaml's init.sql."""
from __future__ import annotations

import json
from typing import Any, Optional
from uuid import UUID

import asyncpg

from . import config

_pool: Optional[asyncpg.Pool] = None


async def init_pool() -> None:
    global _pool
    _pool = await asyncpg.create_pool(
        host=config.POSTGRES_HOST,
        port=config.POSTGRES_PORT,
        database=config.POSTGRES_DB,
        user=config.POSTGRES_USER,
        password=config.POSTGRES_PASSWORD,
        min_size=1,
        max_size=5,
    )


async def close_pool() -> None:
    if _pool is not None:
        await _pool.close()


def _pool_or_raise() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("DB pool not initialized — call init_pool() at startup")
    return _pool


async def create_incident(alert_name: str, service_name: str | None, fault_id: str | None) -> UUID:
    query = """
        INSERT INTO incidents (alert_name, service_name, fault_id, status)
        VALUES ($1, $2, $3, 'open')
        RETURNING id
    """
    async with _pool_or_raise().acquire() as conn:
        row = await conn.fetchrow(query, alert_name, service_name, fault_id)
        return row["id"]


async def update_incident(incident_id: UUID, **fields: Any) -> None:
    if not fields:
        return
    set_clause = ", ".join(f"{key} = ${i + 2}" for i, key in enumerate(fields))
    values = list(fields.values())
    query = f"UPDATE incidents SET {set_clause} WHERE id = $1"
    async with _pool_or_raise().acquire() as conn:
        await conn.execute(query, incident_id, *values)


async def get_incident(incident_id: UUID) -> dict | None:
    async with _pool_or_raise().acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM incidents WHERE id = $1", incident_id)
        return dict(row) if row else None


async def list_incidents(limit: int = 50) -> list[dict]:
    async with _pool_or_raise().acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM incidents ORDER BY created_at DESC LIMIT $1", limit
        )
        return [dict(r) for r in rows]


async def add_step(
    incident_id: UUID,
    step_index: int,
    node_name: str,
    input_data: dict | None,
    output_data: dict | None,
    llm_prompt: str | None = None,
    llm_response: str | None = None,
    tool_calls: list[dict] | None = None,
) -> None:
    query = """
        INSERT INTO incident_steps
            (incident_id, step_index, node_name, finished_at, input, output, llm_prompt, llm_response, tool_calls)
        VALUES ($1, $2, $3, now(), $4, $5, $6, $7, $8)
    """
    async with _pool_or_raise().acquire() as conn:
        await conn.execute(
            query,
            incident_id,
            step_index,
            node_name,
            json.dumps(input_data) if input_data is not None else None,
            json.dumps(output_data) if output_data is not None else None,
            llm_prompt,
            llm_response,
            json.dumps(tool_calls) if tool_calls is not None else None,
        )


async def list_steps(incident_id: UUID) -> list[dict]:
    async with _pool_or_raise().acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM incident_steps WHERE incident_id = $1 ORDER BY step_index",
            incident_id,
        )
        return [dict(r) for r in rows]


async def search_similar_incidents(embedding: list[float], limit: int = 5) -> list[dict]:
    """pgvector cosine-similarity search over past resolved incidents."""
    vector_literal = "[" + ",".join(str(x) for x in embedding) + "]"
    query = """
        SELECT id, alert_name, service_name, root_cause, remediation_action, outcome,
               1 - (embedding <=> $1::vector) AS similarity
        FROM incidents
        WHERE embedding IS NOT NULL
        ORDER BY embedding <=> $1::vector
        LIMIT $2
    """
    async with _pool_or_raise().acquire() as conn:
        rows = await conn.fetch(query, vector_literal, limit)
        return [dict(r) for r in rows]


async def mark_resolved(
    incident_id: UUID,
    status: str,
    outcome: str,
    root_cause: str | None,
    remediation_action: str | None,
) -> None:
    query = """
        UPDATE incidents
        SET status = $2, outcome = $3, root_cause = $4, remediation_action = $5, resolved_at = now()
        WHERE id = $1
    """
    async with _pool_or_raise().acquire() as conn:
        await conn.execute(query, incident_id, status, outcome, root_cause, remediation_action)


async def mark_approved(incident_id: UUID, approved_by: str) -> None:
    query = """
        UPDATE incidents
        SET status = 'remediating', approved_by = $2, approved_at = now()
        WHERE id = $1
    """
    async with _pool_or_raise().acquire() as conn:
        await conn.execute(query, incident_id, approved_by)
