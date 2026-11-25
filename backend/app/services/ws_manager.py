"""
WebSocket Connection Manager — Phase 4 Agent Live Updates.
Broadcasts agent execution events per debugging session_id.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, List
from fastapi import WebSocket

logger = logging.getLogger("forge.ws")


class SessionWebSocketManager:
    def __init__(self) -> None:
        self._connections: Dict[str, List[WebSocket]] = {}
        self._loop: asyncio.AbstractEventLoop | None = None

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    async def connect(self, session_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections.setdefault(session_id, []).append(websocket)

    def disconnect(self, session_id: str, websocket: WebSocket) -> None:
        conns = self._connections.get(session_id, [])
        if websocket in conns:
            conns.remove(websocket)
        if not conns and session_id in self._connections:
            del self._connections[session_id]

    async def broadcast(self, session_id: str, event: Dict[str, Any]) -> None:
        conns = list(self._connections.get(session_id, []))
        dead: List[WebSocket] = []
        payload = json.dumps(event, default=str)
        for ws in conns:
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(session_id, ws)

    def broadcast_sync(self, session_id: str, event: Dict[str, Any]) -> None:
        """Thread-safe helper so background LangGraph threads can emit WS events."""
        if not self._loop or not self._connections.get(session_id):
            return
        try:
            asyncio.run_coroutine_threadsafe(
                self.broadcast(session_id, event),
                self._loop,
            )
        except Exception as exc:
            logger.debug(f"WS broadcast_sync skipped: {exc}")


ws_manager = SessionWebSocketManager()
