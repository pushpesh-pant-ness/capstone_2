"""Historical-incident similarity search (pgvector), used by the `diagnose` node
so the agent can say "this looks like incident X, which was fixed by Y"."""
from __future__ import annotations

from .. import db
from ..llm import bedrock_client


async def find_similar_incidents(summary_text: str, limit: int = 5) -> list[dict]:
    embedding = bedrock_client.embed_text(summary_text)
    return await db.search_similar_incidents(embedding, limit=limit)


async def store_incident_embedding(incident_id, summary_text: str) -> None:
    embedding = bedrock_client.embed_text(summary_text)
    vector_literal = "[" + ",".join(str(x) for x in embedding) + "]"
    await db.update_incident(incident_id, embedding=vector_literal)
