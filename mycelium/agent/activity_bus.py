"""
Real-time agent activity broadcast bus.

Collects structured activity events from the pipeline and all agent subprocesses
and broadcasts them to SSE subscribers so the UI can show a live agent chat view.

thread-safe: emit() may be called from any thread (e.g. ADK agent threads running
inside asyncio.to_thread). Events are scheduled onto the main event loop via
run_coroutine_threadsafe.

Event schema - all events share these fields:
    type   : str   - discriminant (see EVENT TYPES below)
    ts     : float - unix timestamp (time.time())

Plus type-specific fields documented below.

EVENT TYPES
-----------
run_start        run_id
run_end          run_id, status
stage_start      stage_id, label
stage_end        stage_id, label, status, duration_ms
agent_text       stage_id, text
tool_call        stage_id, tool, args
tool_response    stage_id, tool, result
subagent_spawn   stage_id, kind ("member"|"module"|"drift"), subject
subagent_result  stage_id, kind, subject, summary
finding          stage_id, subject, concern_type, narrative
action_planned   stage_id, kind, title
"""
from __future__ import annotations

import asyncio
import time
from collections import deque


class ActivityBus:
    def __init__(self, maxlen: int = 1000) -> None:
        self._buffer: deque[dict] = deque(maxlen=maxlen)
        self._subscribers: set[asyncio.Queue] = set()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._capture_run_id: str | None = None
        self._capture_buffer: list[dict] = []

    # ------------------------------------------------------------------
    # Loop registration (call from the lifespan startup handler)
    # ------------------------------------------------------------------

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    # ------------------------------------------------------------------
    # Emit (thread-safe - safe to call from any thread)
    # ------------------------------------------------------------------

    def emit(self, event: dict) -> None:
        if "ts" not in event:
            event = {**event, "ts": time.time()}
        self._buffer.append(event)
        if self._capture_run_id is not None:
            self._capture_buffer.append(event)
        if self._loop is not None and not self._loop.is_closed():
            try:
                asyncio.run_coroutine_threadsafe(self._broadcast(event), self._loop)
            except Exception:
                pass  # bus errors must never crash the agent

    # ------------------------------------------------------------------
    # Subscription (async, main loop only)
    # ------------------------------------------------------------------

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=200)
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subscribers.discard(q)

    async def _broadcast(self, event: dict) -> None:
        for q in list(self._subscribers):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass  # slow subscriber - drop rather than block

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Clear the buffer. Call at the start of each pipeline run."""
        self._buffer.clear()

    def history(self) -> list[dict]:
        return list(self._buffer)

    # ------------------------------------------------------------------
    # Per-run replay capture
    # ------------------------------------------------------------------

    def start_capture(self, run_id: str) -> None:
        """Begin accumulating all emitted events for this run_id."""
        self._capture_run_id = run_id
        self._capture_buffer = []

    def stop_capture(self) -> list[dict]:
        """Stop accumulating and return the captured event list."""
        events = list(self._capture_buffer)
        self._capture_run_id = None
        self._capture_buffer = []
        return events


# ---------------------------------------------------------------------------
# Module-level singleton - import this everywhere
# ---------------------------------------------------------------------------
bus = ActivityBus()
