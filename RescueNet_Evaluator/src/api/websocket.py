"""
FieldMesh WebSocket Broadcaster.

Manages active browser WebSocket connections and streams live digital twin telemetry
(packets in flight, topology changes, battery updates, and KPIs) to the React/Three.js frontend.
"""

from __future__ import annotations
import asyncio
import json
from typing import Set, Dict, Any
from fastapi import WebSocket, WebSocketDisconnect


class ConnectionManager:
    """Manages connected WebSocket clients."""

    def __init__(self) -> None:
        self.active_connections: Set[WebSocket] = set()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections.add(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        self.active_connections.discard(websocket)

    async def broadcast(self, message: Dict[str, Any]) -> None:
        if not self.active_connections:
            return
        dead = set()
        text = json.dumps(message)
        for conn in self.active_connections:
            try:
                await conn.send_text(text)
            except Exception:
                dead.add(conn)
        for conn in dead:
            self.active_connections.discard(conn)


ws_manager = ConnectionManager()
