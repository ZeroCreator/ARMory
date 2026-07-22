"""In-memory event broker for Server-Sent Events (SSE).

Used to push real-time kanban updates to connected browsers.
"""

import asyncio
from typing import Any

_subscribers: list[asyncio.Queue[dict[str, Any]]] = []


def subscribe() -> asyncio.Queue[dict[str, Any]]:
    """Create a new event queue and register it."""
    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
    _subscribers.append(queue)
    return queue


def unsubscribe(queue: asyncio.Queue[dict[str, Any]]) -> None:
    """Remove a queue from the subscriber list."""
    if queue in _subscribers:
        _subscribers.remove(queue)


def broadcast(event: dict[str, Any]) -> None:
    """Send an event to all active subscribers."""
    for queue in _subscribers:
        try:
            queue.put_nowait(event)
        except asyncio.QueueFull:
            pass
