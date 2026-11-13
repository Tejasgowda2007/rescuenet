"""
Bluetooth Low Energy (BLE) Transport Stub.

Design Decisions:
1. Future Hardware Support:
   - In dense disaster debris, Wi-Fi routers may not have line-of-sight.
   - BLE 5.0 (2 Mbps PHY) allows direct ad-hoc peer pairing between phones
     and field laptops using GATT characteristics or L2CAP connection-oriented channels.
2. Architecture Decoupling:
   - Because the core sync protocol is transport-independent, swapping TCP
     for BLE requires zero modifications to the Node, Storage, or Sync layers.
"""

from __future__ import annotations
from typing import Dict, Any, Callable, Optional
from .base import Transport, TransportMessage


class BLEStubTransport(Transport):
    """
    Mock/Stub transport demonstrating Bluetooth Low Energy integration.
    """

    def __init__(self, node_id: str, ble_address: str = "00:11:22:33:44:55") -> None:
        self.node_id = node_id
        self.ble_address = ble_address
        self.handler: Optional[Callable[[TransportMessage], Optional[TransportMessage]]] = None
        self._total_bytes: int = 0
        self._total_messages: int = 0

    def register_node(
        self,
        node_id: str,
        handler: Callable[[TransportMessage], Optional[TransportMessage]]
    ) -> None:
        self.node_id = node_id
        self.handler = handler

    def unregister_node(self, node_id: str) -> None:
        self.handler = None

    def send(self, message: TransportMessage) -> Optional[TransportMessage]:
        """
        Placeholder: in a hardware-backed implementation, this would:
        1. Discover target BLE peripheral via Advertisement scan (UUID filter).
        2. Connect to peripheral and negotiate MTU size (e.g. 512 bytes).
        3. Write framed chunks to Sync TX characteristic (UUID: 0xFF01).
        4. Read response chunks from Sync RX characteristic (UUID: 0xFF02).
        """
        # For now, return None simulating no physical BLE hardware connected
        return None

    def get_stats(self) -> Dict[str, int]:
        return {
            "total_bytes": self._total_bytes,
            "total_messages": self._total_messages,
        }

    def reset_stats(self) -> None:
        self._total_bytes = 0
        self._total_messages = 0
