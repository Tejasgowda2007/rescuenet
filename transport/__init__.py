"""
RescueNet Transport Package
Pluggable network transports: in-memory, TCP (LAN), and BLE stubs.
"""

from .base import Transport, TransportMessage
from .in_memory import InMemoryTransport

__all__ = ["Transport", "TransportMessage", "InMemoryTransport"]
