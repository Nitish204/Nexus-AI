"""
NEXUS — Real-time event bus.

Agents don't know or care that a UI exists. They just call `publish()`.
Anyone listening (WebSocket connections, log recorders, future Slack
bots) subscribes independently. This keeps the agent layer UI-agnostic
and testable without a browser attached.
"""
import asyncio
import json
from collections import defaultdict
from typing import Any


class EventBus:
    def __init__(self) -> None:
        self._subscribers: dict[str, set[asyncio.Queue]] = defaultdict(set)

    async def subscribe(self, project_id: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._subscribers[project_id].add(q)
        return q

    def unsubscribe(self, project_id: str, q: asyncio.Queue) -> None:
        # `self._subscribers` is a defaultdict(set) — plain attribute
        # access via `[project_id]` auto-vivifies an empty set entry
        # for any project_id it's called with, including ones that
        # already have zero subscribers. Every WebSocket disconnect
        # was therefore leaving a permanent (if empty) dict entry
        # behind, one per project ever opened, for the life of the
        # process. Using .get() avoids creating that entry, and the
        # dict key is dropped entirely once the set empties out.
        subscribers = self._subscribers.get(project_id)
        if subscribers is None:
            return
        subscribers.discard(q)
        if not subscribers:
            del self._subscribers[project_id]

    async def publish(self, project_id: str, event_type: str, payload: dict[str, Any]) -> None:
        message = json.dumps({"type": event_type, "payload": payload})
        for q in list(self._subscribers.get(project_id, [])):
            await q.put(message)


# Single process-wide instance. For multi-worker deployments, swap this
# for a Redis pub/sub backed implementation (same interface).
event_bus = EventBus()
