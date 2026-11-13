"""
Optional WebSocket real-time sync bridge.

Runs alongside the offline-first core. When any device reaches the internet,
it can push/pull deltas over a websocket instead of waiting for physical encounters.
Fully optional; the system works without it.
"""
from __future__ import annotations
import asyncio
import json
from typing import Dict, Any

try:
    import websockets
except Exception:  # pragma: no cover
    websockets = None


class WSSyncServer:
    def __init__(self, node: Any, host: str = "0.0.0.0", port: int = 8765) -> None:
        self.node = node
        self.host = host
        self.port = port
        self.clients: set = set()

    async def handler(self, websocket) -> None:
        self.clients.add(websocket)
        try:
            async for raw in websocket:
                msg = json.loads(raw)
                if msg.get("type") == "pull":
                    vv = msg.get("version_vector", {})
                    events = self.node.store.get_events_since(vv)
                    await websocket.send(json.dumps({
                        "type": "delta",
                        "events": [e.to_dict() for e in events],
                        "version_vector": self.node.get_version_vector(),
                    }))
                elif msg.get("type") == "push":
                    from events.event import Event
                    evs = [Event.from_dict(d) for d in msg.get("events", [])]
                    self.node.store.append_many(evs)
                    await websocket.send(json.dumps({"type": "ack", "ingested": len(evs)}))
        finally:
            self.clients.discard(websocket)

    async def serve(self) -> None:
        if websockets is None:
            raise RuntimeError("websockets not installed")
        async with websockets.serve(self.handler, self.host, self.port):
            await asyncio.Future()  # run forever