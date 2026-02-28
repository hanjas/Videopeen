from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages per-project WebSocket connections for progress updates."""

    def __init__(self) -> None:
        # project_id → set of active websocket connections
        self._connections: dict[str, set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, project_id: str, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._connections.setdefault(project_id, set()).add(ws)
        logger.info("WS connected for project %s (total=%d)", project_id, len(self._connections.get(project_id, [])))

    async def disconnect(self, project_id: str, ws: WebSocket) -> None:
        async with self._lock:
            conns = self._connections.get(project_id)
            if conns:
                conns.discard(ws)
                if not conns:
                    del self._connections[project_id]

    async def send_progress(self, project_id: str, data: dict[str, Any]) -> None:
        """Broadcast a progress payload to all listeners of a project."""
        async with self._lock:
            conns = list(self._connections.get(project_id, []))

        payload = json.dumps(data)
        dead: list[WebSocket] = []
        for ws in conns:
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)

        # Clean up dead connections
        if dead:
            async with self._lock:
                bucket = self._connections.get(project_id)
                if bucket:
                    for ws in dead:
                        bucket.discard(ws)


ws_manager = ConnectionManager()
