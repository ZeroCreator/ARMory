"""SSE endpoint for real-time kanban updates."""

import asyncio
import datetime
import json
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.config import get_settings
from app.events import subscribe, unsubscribe

router = APIRouter(prefix="/api", tags=["events"])


HEARTBEAT_INTERVAL = 15.0
settings = get_settings()


async def _event_stream(request: Request):
    queue = subscribe()
    client_date = request.headers.get("last-event-id") or request.query_params.get("daily_date")
    try:
        current_date = datetime.date.fromisoformat(client_date) if client_date else None
    except ValueError:
        current_date = None
    try:
        while True:
            if await request.is_disconnected():
                break

            today = datetime.datetime.now(ZoneInfo(settings.timezone)).date()
            if today != current_date:
                current_date = today
                data = json.dumps({"event": "daily", "date": today.isoformat()}, ensure_ascii=False)
                yield f"id: {today.isoformat()}\nevent: daily\ndata: {data}\n\n"

            try:
                event = await asyncio.wait_for(queue.get(), timeout=HEARTBEAT_INTERVAL)
                event_name = event.get("event", "kanban")
                data = json.dumps(event, ensure_ascii=False)
                yield f"event: {event_name}\ndata: {data}\n\n"
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
