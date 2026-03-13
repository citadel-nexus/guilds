# src/streaming/emitter.py
"""
Server-Sent Events (SSE) pipeline event streaming.

PipelineEventEmitter broadcasts stage updates as events process.
SSE clients (dashboard, CLI) subscribe via event_id.

Usage in orchestrator:
    emitter = PipelineEventEmitter()
    emitter.emit(event_id, "sentinel", "running", {"classification": "ci_failed"})

Usage in FastAPI:
    @app.get("/pipeline/{event_id}/stream")
    async def stream(event_id: str):
        return emitter.sse_response(event_id)
"""
from __future__ import annotations

import asyncio
import json
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator, Dict, List, Optional


@dataclass
class PipelineEvent:
    event_id: str
    stage: str
    status: str  # "running" | "completed" | "error" | "skipped"
    data: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def to_sse(self) -> str:
        """Format as SSE data line."""
        payload = {
            "event_id": self.event_id,
            "stage": self.stage,
            "status": self.status,
            "data": self.data,
            "timestamp": self.timestamp,
        }
        return f"data: {json.dumps(payload)}\n\n"


_MAX_HISTORY_PER_EVENT = 500
_MAX_COMPLETED_EVENTS = 100


class PipelineEventEmitter:
    """
    Broadcast pipeline events to SSE subscribers.

    Thread-safe for synchronous orchestrator code emitting events
    that async SSE handlers consume.
    """

    def __init__(self) -> None:
        # event_id -> list of events (history)
        self._history: Dict[str, List[PipelineEvent]] = defaultdict(list)
        # event_id -> list of asyncio.Queue for live subscribers
        self._subscribers: Dict[str, List[asyncio.Queue]] = defaultdict(list)
        # Track completed event_ids for automatic cleanup
        self._completed_events: List[str] = []

    def emit(
        self,
        event_id: str,
        stage: str,
        status: str,
        data: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Emit a pipeline event. Called from orchestrator (sync context)."""
        evt = PipelineEvent(
            event_id=event_id,
            stage=stage,
            status=status,
            data=data or {},
        )
        history = self._history[event_id]
        history.append(evt)

        # Trim per-event history to prevent unbounded growth
        if len(history) > _MAX_HISTORY_PER_EVENT:
            self._history[event_id] = history[-_MAX_HISTORY_PER_EVENT:]

        # Auto-cleanup oldest completed pipelines
        if stage == "pipeline" and status == "completed":
            self._completed_events.append(event_id)
            if len(self._completed_events) > _MAX_COMPLETED_EVENTS:
                oldest = self._completed_events.pop(0)
                self._history.pop(oldest, None)
                self._subscribers.pop(oldest, None)

        # Push to any live subscribers
        for queue in self._subscribers.get(event_id, []):
            try:
                queue.put_nowait(evt)
            except asyncio.QueueFull:
                pass  # Drop if subscriber is slow

    def get_history(self, event_id: str) -> List[Dict[str, Any]]:
        """Get all events for a pipeline run."""
        return [
            {
                "stage": e.stage,
                "status": e.status,
                "data": e.data,
                "timestamp": e.timestamp,
            }
            for e in self._history.get(event_id, [])
        ]

    async def subscribe(
        self, event_id: str, max_idle_keepalives: int = 20,
    ) -> AsyncGenerator[PipelineEvent, None]:
        """Subscribe to live events for a pipeline. Used by SSE endpoint.

        Args:
            event_id: Pipeline event ID to subscribe to.
            max_idle_keepalives: Max consecutive keepalives before auto-disconnect
                                (default 20 = 10 min at 30s intervals).
        """
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._subscribers[event_id].append(queue)
        idle_count = 0

        try:
            # First replay history
            for evt in self._history.get(event_id, []):
                yield evt

            # Then stream live
            while True:
                try:
                    evt = await asyncio.wait_for(queue.get(), timeout=30.0)
                    idle_count = 0  # Reset on real event
                    yield evt
                    if evt.stage == "pipeline" and evt.status == "completed":
                        break
                except asyncio.TimeoutError:
                    idle_count += 1
                    if idle_count >= max_idle_keepalives:
                        break
                    # Send keepalive
                    yield PipelineEvent(
                        event_id=event_id,
                        stage="keepalive",
                        status="alive",
                    )
        finally:
            if queue in self._subscribers.get(event_id, []):
                self._subscribers[event_id].remove(queue)

    async def sse_generator(self, event_id: str) -> AsyncGenerator[str, None]:
        """Generate SSE-formatted strings for a FastAPI StreamingResponse."""
        async for evt in self.subscribe(event_id):
            yield evt.to_sse()


# Singleton for the application
pipeline_emitter = PipelineEventEmitter()
