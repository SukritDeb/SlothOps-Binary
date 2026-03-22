"""
SlothOps Engine — SSE Manager
Manages Server-Sent Events broadcasting to connected dashboard clients.
Uses an asyncio.Queue per client for fan-out.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, AsyncGenerator

logger = logging.getLogger("slothops.sse")

# Connected client queues
_clients: list[asyncio.Queue] = []


async def broadcast(event_type: str, payload: dict[str, Any]) -> None:
    """
    Push an event to every connected SSE client.

    Args:
        event_type: SSE event name (e.g. "status_update", "issue_created").
        payload: JSON-serialisable dict sent as the event data.
    """
    message = {
        "event": event_type,
        "data": payload,
    }
    disconnected: list[asyncio.Queue] = []
    for q in _clients:
        try:
            q.put_nowait(message)
        except asyncio.QueueFull:
            disconnected.append(q)

    # Clean up any full / dead queues
    for q in disconnected:
        _clients.remove(q)


async def subscribe() -> AsyncGenerator[dict, None]:
    """
    Yield SSE messages for a single client connection.

    Usage inside a FastAPI SSE endpoint::

        @app.get("/stream")
        async def stream():
            async def gen():
                async for msg in subscribe():
                    yield msg
            return EventSourceResponse(gen())
    """
    q: asyncio.Queue = asyncio.Queue(maxsize=256)
    _clients.append(q)
    try:
        while True:
            msg = await q.get()
            yield msg
    finally:
        _clients.remove(q)
