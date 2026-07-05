"""
Server-Sent Events API for Real-Time Updates

Provides an SSE endpoint for the frontend to receive real-time notifications
when data changes (via MCP or API).
"""

import json
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
import structlog

from app.core.events import event_bus

router = APIRouter()
logger = structlog.get_logger()


@router.get("/events")
async def event_stream():
    """
    Subscribe to server-sent events for real-time updates.

    Event types:
    - agent.created, agent.updated, agent.deleted
    - source.created, source.indexed, source.deleted
    """
    logger.info("SSE client connected")

    async def generate():
        try:
            async for event in event_bus.subscribe():
                data = json.dumps(event.to_dict())
                yield f"data: {data}\n\n"
        except Exception as e:
            logger.error("SSE stream error", error=str(e))
            raise
        finally:
            logger.info("SSE client disconnected")

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/events/status")
async def event_status():
    """Get the current status of the event system."""
    return {"subscribers": event_bus.subscriber_count}
