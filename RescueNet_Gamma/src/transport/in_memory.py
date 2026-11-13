"""
In-Memory Transport Implementation.

Used for the simulator, proof harness, and unit testing.
Simulates network links between in-process nodes with partition support
and strict wire-level serialization for accurate byte accounting.
"""

from __future__ import annotations
from typing import Dict, Set, Tuple, Callable, Optional
from .base import Transport, TransportMessage


class InMemoryTransport(Transport):
    """
    Direct in-memory message bus connecting multiple simulated devices.

    Design Decision:
    - Even though messages stay inside Python memory, every message is converted
      to canonical UTF-8 bytes (`msg.to_bytes()`) and reconstructed.
      This verifies real serialization compatibility and provides 100% accurate
      wire byte counts.
    - Built-in partition matrix allows simulating network cuts and link healing.
    """

    def __init__(self) -> None:
        self._handlers: Dict[str, Callable[[TransportMessage], Optional[TransportMessage]]] = {}
        # Stores directed or undirected blocked links: (node_a, node_b)
        self._blocked_links: Set[Tuple[str, str]] = set()
        self._total_bytes_transferred: int = 0
        self._total_messages_sent: int = 0

    def register_node(
        self,
        node_id: str,
        handler: Callable[[TransportMessage], Optional[TransportMessage]]
    ) -> None:
        """Register an active node and its incoming message listener."""
        self._handlers[node_id] = handler

    def unregister_node(self, node_id: str) -> None:
        """Remove a node from the network."""
        self._handlers.pop(node_id, None)

    def cut_link(self, node_a: str, node_b: str) -> None:
        """Simulate a network split between two nodes (bi-directional cut)."""
        self._blocked_links.add((node_a, node_b))
        self._blocked_links.add((node_b, node_a))

    def heal_link(self, node_a: str, node_b: str) -> None:
        """Restore network connectivity between two nodes."""
        self._blocked_links.discard((node_a, node_b))
        self._blocked_links.discard((node_b, node_a))

    def heal_all(self) -> None:
        """Clear all partitions across the entire network."""
        self._blocked_links.clear()

    def is_connected(self, node_a: str, node_b: str) -> bool:
        """Check if message delivery between two nodes is physically possible."""
        if (node_a, node_b) in self._blocked_links:
            return False
        return node_a in self._handlers and node_b in self._handlers

    def send(self, message: TransportMessage) -> Optional[TransportMessage]:
        """
        Deliver message from sender to recipient.
        Returns the immediate response message if the handler provides one.
        """
        sender = message.sender_id
        recipient = message.recipient_id

        # Check partition boundary
        if not self.is_connected(sender, recipient):
            # Message is dropped due to network partition
            return None

        handler = self._handlers[recipient]

        # Serialize to actual wire bytes to measure exact network bandwidth
        out_bytes = message.to_bytes()
        self._total_bytes_transferred += len(out_bytes)
        self._total_messages_sent += 1

        # Reconstruct on receiving end (simulating real wire reception)
        in_message = TransportMessage.from_bytes(out_bytes)
        response = handler(in_message)

        if response is not None:
            # Check return path connectivity
            if not self.is_connected(recipient, sender):
                return None

            resp_bytes = response.to_bytes()
            self._total_bytes_transferred += len(resp_bytes)
            self._total_messages_sent += 1
            return TransportMessage.from_bytes(resp_bytes)

        return None

    def get_stats(self) -> Dict[str, int]:
        """Return cumulative network transfer statistics."""
        return {
            "total_bytes": self._total_bytes_transferred,
            "total_messages": self._total_messages_sent,
        }

    def reset_stats(self) -> None:
        """Reset network counters to zero."""
        self._total_bytes_transferred = 0
        self._total_messages_sent = 0
