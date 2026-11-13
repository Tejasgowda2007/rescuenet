"""
Drone / Vehicle Relay Mesh Transport.

Innovative: uses UAVs, ambulances, or any moving vehicle as physical data mules
carrying encrypted sync bundles between disconnected camps. The vehicle's onboard
computer (or a phone taped to the dashboard) syncs with each camp it visits,
acting as a mobile relay. No radio infrastructure required; works across any
distance the vehicle can travel.

This complements the in-app "Ambulance Data Mule" with a first-class transport
that auto-syncs whenever a relay comes within range.
"""
from __future__ import annotations
import json
from typing import Dict, Any, Callable, Optional, List
from .base import Transport, TransportMessage


class DroneRelayTransport(Transport):
    def __init__(self, node_id: str, vehicle_id: str = "drone-1", max_payload_bytes: int = 1_000_000) -> None:
        self.node_id = node_id
        self.vehicle_id = vehicle_id
        self.max_payload_bytes = max_payload_bytes
        self.handler: Optional[Callable[[TransportMessage], Optional[TransportMessage]]] = None
        self._total_bytes = 0
        self._total_messages = 0
        self.buffer: List[TransportMessage] = []  # queued bundles for next drop

    def register_node(self, node_id, handler):
        self.node_id = node_id
        self.handler = handler

    def unregister_node(self, node_id):
        self.handler = None

    def send(self, message: TransportMessage) -> Optional[TransportMessage]:
        self._total_bytes += message.wire_byte_size()
        self._total_messages += 1
        self.buffer.append(message)
        # Simulation: deliver immediately (real: queued until vehicle reaches peer)
        if self.handler is not None:
            return self.handler(message)
        return None

    def flush_to_camp(self, camp_handler) -> int:
        """Called when the drone lands at a camp: dump all buffered bundles."""
        n = 0
        for msg in list(self.buffer):
            camp_handler(msg)
            n += 1
        self.buffer.clear()
        return n

    def get_stats(self) -> Dict[str, int]:
        return {"total_bytes": self._total_bytes, "total_messages": self._total_messages, "buffered": len(self.buffer), "vehicle": self.vehicle_id}

    def reset_stats(self) -> None:
        self._total_bytes = 0
        self._total_messages = 0
        self.buffer.clear()