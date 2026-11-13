"""
Li-Fi (Light Fidelity) / Visible Light Communication Transport Stub.

Innovative: transmits sync data by modulating LED/screen brightness at rates
invisible to the human eye. Receivers use a camera or photodiode. Works in
RF-jammed or RF-denied environments (e.g., inside metal bunkers, hospitals
with RF restrictions, or where radio is illegal/blocked).

Range: meters to tens of meters depending on LED power and receiver sensitivity.
Bandwidth: kbps to Mbps with high-speed LEDs.
"""
from __future__ import annotations
import json
from dataclasses import asdict
from typing import Dict, Any, Callable, Optional
from .base import Transport, TransportMessage


class LiFiTransport(Transport):
    def __init__(self, node_id: str, led_pin: int = 18, camera_index: int = 0, modulation: str = "ook") -> None:
        self.node_id = node_id
        self.led_pin = led_pin
        self.camera_index = camera_index
        self.modulation = modulation  # ook | vppm | csK
        self.handler: Optional[Callable[[TransportMessage], Optional[TransportMessage]]] = None
        self._total_bytes = 0
        self._total_messages = 0
        self.last_light_pattern: str = ""

    def register_node(self, node_id, handler):
        self.node_id = node_id
        self.handler = handler

    def unregister_node(self, node_id):
        self.handler = None

    def send(self, message: TransportMessage) -> Optional[TransportMessage]:
        raw = json.dumps(asdict(message), sort_keys=True, separators=(",", ":"))
        # Simulate modulating each byte as light pulses
        self.last_light_pattern = "".join(f"{ord(c):08b}" for c in raw)
        self._total_bytes += len(raw.encode("utf-8"))
        self._total_messages += 1
        # In real hardware: toggle LED per bit; camera captures & decodes.
        # Simulation: deliver directly for round-trip fidelity.
        if self.handler is not None:
            return self.handler(message)
        return None

    def get_stats(self) -> Dict[str, int]:
        return {"total_bytes": self._total_bytes, "total_messages": self._total_messages, "modulation": self.modulation}

    def reset_stats(self) -> None:
        self._total_bytes = 0
        self._total_messages = 0