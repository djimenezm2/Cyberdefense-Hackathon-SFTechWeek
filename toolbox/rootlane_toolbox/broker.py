import asyncio
from typing import Any

Message = tuple[str, dict[str, Any]]


class Broker:
    """In-process fan-out of named events to bounded per-subscriber queues."""

    def __init__(self, maxsize: int = 100):
        self._maxsize = maxsize
        self._subscribers: dict[asyncio.Queue, asyncio.AbstractEventLoop] = {}

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)

    def subscribe(self) -> asyncio.Queue:
        """Register a subscriber on the running loop and return its queue of (event, data)."""
        queue: asyncio.Queue = asyncio.Queue(maxsize=self._maxsize)
        self._subscribers[queue] = asyncio.get_running_loop()
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        """Remove a subscriber; unknown queues are ignored."""
        self._subscribers.pop(queue, None)

    def publish(self, event: str, data: dict[str, Any]) -> None:
        """
        Deliver an event to every subscriber without blocking.

        Safe to call from any thread. A full queue drops its oldest message.

        Args:
            event (str): The event name.
            data (dict[str, Any]): The JSON-serializable payload.
        """
        for queue, loop in list(self._subscribers.items()):
            try:
                loop.call_soon_threadsafe(self._put, queue, (event, data))
            except RuntimeError:
                self._subscribers.pop(queue, None)

    @staticmethod
    def _put(queue: asyncio.Queue, message: Message) -> None:
        if queue.full():
            queue.get_nowait()
        queue.put_nowait(message)


broker = Broker()
