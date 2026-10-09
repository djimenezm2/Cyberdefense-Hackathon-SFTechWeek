import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from ..core.broker import Broker
from .deps import get_broker, get_ping_interval

stream_router = APIRouter()


def format_sse(event: str, data: dict[str, Any]) -> str:
    """Render one server-sent event message."""
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


async def event_stream(broker: Broker, ping_interval_s: float) -> AsyncIterator[str]:
    """
    Yield SSE messages for one subscriber until the generator is closed.

    Args:
        broker (Broker): The broker to subscribe to.
        ping_interval_s (float): Idle seconds before a `ping` event is sent.

    Yields:
        str: One formatted SSE message per published event or idle interval.
    """
    queue = broker.subscribe()
    try:
        while True:
            try:
                event, data = await asyncio.wait_for(queue.get(), timeout=ping_interval_s)
            except asyncio.TimeoutError:
                event, data = "ping", {}
            yield format_sse(event, data)
    finally:
        broker.unsubscribe(queue)


@stream_router.get("/api/stream")
async def stream(broker: Broker = Depends(get_broker), ping_s: float = Depends(get_ping_interval)):
    """Server-sent events: verdict, step, incident_update and ping."""
    return StreamingResponse(
        event_stream(broker, ping_s),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
