"""SSE endpoint for real-time kanban updates."""

import asyncio
import json

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.events import subscribe, unsubscribe

router = APIRouter(prefix="/api", tags=["events"])


HEARTBEAT_INTERVAL = 15.0


async def _event_stream(request: Request):
    queue = subscribe()
    try:
        while True:
            if await request.is_disconnected():
                break

            try:
                event = await asyncio.wait_for(queue.get(), timeout=HEARTBEAT_INTERVAL)
                data = json.dumps(event, ensure_ascii=False)
                yield f"event: kanban\ndata: {data}\n\n"
            except asyncio.TimeoutError:
                yield ":heartbeat\n\n"
    finally:
        unsubscribe(queue)


@router.get("/events")
async def events_endpoint(request: Request):
    """Server-Sent Events stream for kanban updates."""
    return StreamingResponse(
        _event_stream(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
