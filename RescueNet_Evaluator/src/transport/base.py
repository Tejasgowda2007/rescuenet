"""
Abstract Transport Interface and Wire Messaging Envelopes.

Design Decisions:
1. Transport Agnostic: The sync protocol has zero knowledge of whether it runs
   over shared memory, raw TCP sockets, or BLE.
2. Exact Wire Accounting: Every message must serialize to deterministic UTF-8 bytes
   before transmission so the transport can measure real-world bandwidth consumption.
"""

from __future__ import annotations
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, asdict
from typing import Dict, Any, Callable, Optional


@dataclass(frozen=True)
class TransportMessage:
    """
    Standard wire frame envelope used by all transports.
    """
    sender_id: str
    recipient_id: str
    message_type: str       # e.g. "SYNC_REQUEST", "SYNC_RESPONSE", "SYNC_DELTA"
    payload: Dict[str, Any]

    def to_bytes(self) -> bytes:
        """
        Serialize message to canonical bytes.
        Design Decision:
        Using compact JSON separators (',', ':') and UTF-8 encoding ensures
        consistent wire size across Python versions and OS platforms.
        """
        raw_str = json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))
        return raw_str.encode("utf-8")

    @classmethod
    def from_bytes(cls, data: bytes) -> TransportMessage:
        """Deserialize from wire bytes."""
        obj = json.loads(data.decode("utf-8"))
        return cls(
            sender_id=obj["sender_id"],
            recipient_id=obj["recipient_id"],
            message_type=obj["message_type"],
            payload=dict(obj["payload"]),
        )

    def wire_byte_size(self) -> int:
        """Calculate the exact size in bytes this message consumes on the wire."""
        return len(self.to_bytes())


class Transport(ABC):
    """
    Abstract interface for point-to-point and mesh network communication.
    """

    @abstractmethod
    def register_node(
        self,
        node_id: str,
        handler: Callable[[TransportMessage], Optional[TransportMessage]]
    ) -> None:
        """Register a node and its incoming message callback."""
        pass

    @abstractmethod
    def unregister_node(self, node_id: str) -> None:
        """Unregister a node (e.g. node shutdown)."""
        pass

    @abstractmethod
    def send(self, message: TransportMessage) -> Optional[TransportMessage]:
        """
        Send a message to the target recipient.
        Returns the immediate response if synchronous (like RPC), or None if asynchronous.
        """
        pass

    @abstractmethod
    def get_stats(self) -> Dict[str, int]:
        """Returns total bytes and messages sent across this transport."""
        pass

    @abstractmethod
    def reset_stats(self) -> None:
        """Reset byte and message counters."""
        pass
