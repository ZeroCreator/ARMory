"""In-memory event broker for Server-Sent Events (SSE).

Used to push real-time kanban updates to connected browsers.
"""

import asyncio
from typing import Any

_subscribers: list[asyncio.Queue[dict[str, Any]]] = []
_EVENT_QUEUE_MAXSIZE = 256


def subscribe() -> asyncio.Queue[dict[str, Any]]:
    """Create a new event queue and register it."""
    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=_EVENT_QUEUE_MAXSIZE)
    _subscribers.append(queue)
    return queue


def unsubscribe(queue: asyncio.Queue[dict[str, Any]]) -> None:
    """Remove a queue from the subscriber list."""
    if queue in _subscribers:
        _subscribers.remove(queue)


def broadcast(event: dict[str, Any]) -> None:
    """Send an event to all active subscribers."""
    for queue in tuple(_subscribers):
        if queue.full():
            try:
                queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
        try:
            queue.put_nowait(event)
        except asyncio.QueueFull:
            pass
