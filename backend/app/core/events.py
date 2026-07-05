"""
Event Bus for Real-Time UI Updates

Provides a pub/sub mechanism for broadcasting events to connected clients.
Used to notify the frontend when MCP tools modify data.
"""

import asyncio
from asyncio import Queue
from datetime import datetime
from typing import AsyncGenerator, Optional
from dataclasses import dataclass
import structlog

logger = structlog.get_logger()


@dataclass
class StudioEvent:
    """An event to be broadcast to subscribers."""

    type: str  # e.g., "agent.created", "knowledge.indexed"
    payload: dict  # Event-specific data
    source: str = "api"  # "mcp", "api", or "system"
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.utcnow().isoformat()

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "payload": self.payload,
            "source": self.source,
            "timestamp": self.timestamp,
        }


class EventBus:
    """
    In-memory event bus for broadcasting events to subscribers.

    Subscribers receive events via async generators. Events are broadcast
    to all connected subscribers.
    """

    def __init__(self, max_queue_size: int = 100):
        """
        Initialize the event bus.

        Args:
            max_queue_size: Maximum events to queue per subscriber before dropping
        """
        self._subscribers: list[Queue] = []
        self._max_queue_size = max_queue_size
        self._lock = asyncio.Lock()

    async def publish(
        self,
        event_type: str,
        payload: dict,
        source: str = "api",
    ) -> None:
        """
        Publish an event to all subscribers.

        Args:
            event_type: Event type (e.g., "agent.created")
            payload: Event payload data
            source: Event source ("mcp", "api", or "system")
        """
        event = StudioEvent(
            type=event_type,
            payload=payload,
            source=source,
        )

        async with self._lock:
            for queue in self._subscribers:
                if queue.qsize() < self._max_queue_size:
                    await queue.put(event)
                else:
                    logger.warning(
                        "Event queue full, dropping event",
                        event_type=event_type,
                        queue_size=queue.qsize(),
                    )

        logger.debug(
            "Event published",
            event_type=event_type,
            source=source,
            subscribers=len(self._subscribers),
        )

    async def subscribe(self) -> AsyncGenerator[StudioEvent, None]:
        """
        Subscribe to events.

        Yields events as they are published. The subscription is automatically
        cleaned up when the generator is closed.

        Yields:
            StudioEvent objects as they are published
        """
        queue: Queue = Queue(maxsize=self._max_queue_size)

        async with self._lock:
            self._subscribers.append(queue)
            logger.debug("Subscriber added", total=len(self._subscribers))

        try:
            while True:
                event = await queue.get()
                yield event
        finally:
            async with self._lock:
                if queue in self._subscribers:
                    self._subscribers.remove(queue)
                    logger.debug("Subscriber removed", total=len(self._subscribers))

    @property
    def subscriber_count(self) -> int:
        """Return the number of active subscribers."""
        return len(self._subscribers)


# Global event bus instance
event_bus = EventBus()


# Convenience functions for common event types
async def publish_agent_event(
    action: str,  # "created", "updated", "deleted"
    agent_id: str,
    agent_data: Optional[dict] = None,
    source: str = "api",
) -> None:
    """Publish an agent-related event."""
    await event_bus.publish(
        event_type=f"agent.{action}",
        payload={"id": agent_id, **(agent_data or {})},
        source=source,
    )


async def publish_source_event(
    action: str,  # "created", "indexed", "deleted"
    source_id: str,
    source_data: Optional[dict] = None,
    source: str = "api",
) -> None:
    """Publish a source event."""
    await event_bus.publish(
        event_type=f"source.{action}",
        payload={"id": source_id, **(source_data or {})},
        source=source,
    )


# Backward-compatible alias
async def publish_knowledge_event(
    action: str,  # "created", "indexed", "deleted"
    source_id: str,
    source_data: Optional[dict] = None,
    source: str = "api",
) -> None:
    """Publish a knowledge source event (deprecated — use publish_source_event)."""
    await publish_source_event(action, source_id, source_data, source)


async def publish_extension_event(
    action: str,  # "loaded", "reloaded"
    extensions: list[str],
    source: str = "system",
) -> None:
    """Publish an extension event."""
    await event_bus.publish(
        event_type=f"extension.{action}",
        payload={"extensions": extensions},
        source=source,
    )
