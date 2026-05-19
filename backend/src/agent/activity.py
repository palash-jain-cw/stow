from __future__ import annotations

import asyncio
import contextvars

# Set before each orchestrator.run() call; tool functions read it to emit progress.
_progress_queue: contextvars.ContextVar[asyncio.Queue[str | None] | None] = (
    contextvars.ContextVar("_progress_queue", default=None)
)


async def emit(label: str) -> None:
    """Emit a progress label. No-op when no queue is active (e.g. in tests)."""
    q = _progress_queue.get()
    if q is not None:
        await q.put(label)
