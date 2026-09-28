"""In-process pub/sub event bus, so the live demo UI can stream every agent step
in real time (SSE) as it happens — see ARCHITECTURE.md section 8.

Single-process only (fine for this demo: one agent-service replica). If this
service is ever scaled to >1 replica, this needs to move to Postgres LISTEN/NOTIFY
or a real message bus instead.
"""
from __future__ import annotations

import asyncio
import json
import time
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class StepEvent:
    incident_id: str
    node_name: str
    status: str  # started|finished|failed
    timestamp: float = field(default_factory=time.time)
    input: dict[str, Any] | None = None
    output: dict[str, Any] | None = None
    llm_prompt: str | None = None
    llm_response: str | None = None
    tool_calls: list[dict[str, Any]] | None = None
    error: str | None = None

    def to_sse(self) -> str:
        return f"data: {json.dumps(asdict(self))}\n\n"


class EventBus:
    def __init__(self) -> None:
        self._subscribers: dict[str, set[asyncio.Queue]] = {}

    def subscribe(self, incident_id: str) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._subscribers.setdefault(incident_id, set()).add(queue)
        return queue

    def unsubscribe(self, incident_id: str, queue: asyncio.Queue) -> None:
        subs = self._subscribers.get(incident_id)
        if subs and queue in subs:
            subs.discard(queue)

    async def publish(self, event: StepEvent) -> None:
        for queue in list(self._subscribers.get(event.incident_id, set())):
            if queue.full():
                continue
            await queue.put(event)


bus = EventBus()
