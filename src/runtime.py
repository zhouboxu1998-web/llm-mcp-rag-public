from __future__ import annotations

import time
import uuid
from contextlib import asynccontextmanager
from typing import AsyncIterator

from .models import RuntimeEvent


class RuntimeTrace:
    def __init__(self) -> None:
        self.trace_id = uuid.uuid4().hex
        self.events: list[RuntimeEvent] = []

    @asynccontextmanager
    async def step(self, event_type: str, name: str, metadata: dict | None = None) -> AsyncIterator[None]:
        start = time.perf_counter()
        error: str | None = None
        try:
            yield
        except Exception as exc:
            error = str(exc)
            raise
        finally:
            finish = time.perf_counter()
            self.events.append(
                RuntimeEvent(
                    trace_id=self.trace_id,
                    event_type=event_type,
                    name=name,
                    started_at=start,
                    finished_at=finish,
                    metadata=metadata or {},
                    error=error,
                )
            )
