"""
Event model representing an immutable state transition in the disaster response log.
Every real-world action (person found, shelter opened, supply allocated) is captured as an Event.
"""

from __future__ import annotations
import json
import hashlib
from dataclasses import dataclass, field, asdict
from typing import Any, Dict


@dataclass(frozen=True)
class Event:
    """
    An immutable fact recorded by a disaster response node.

    Design Decision:
    - We use frozen=True because an event is a historical fact. Once created,
      no field can ever be altered. History can only be appended to.
    - Fields align strictly with the design spec:
      {event_id, node_id, counter, timestamp, entity_type, entity_id, operation, payload, signature}
    """
    node_id: str             # Unique ID of device/volunteer generating this event (e.g. "laptop-alpha")
    counter: int             # Monotonically increasing sequence number on this node (1, 2, 3...)
    timestamp: float         # POSIX epoch timestamp when the event was recorded locally
    entity_type: str         # Domain entity: "person", "need", "supply", "shelter", "allocation"
    entity_id: str           # Unique identifier for the entity instance
    operation: str           # Action type: "CREATE", "UPDATE", "RESOLVE", "TOMBSTONE"
    payload: Dict[str, Any]  # Arbitrary domain attributes (e.g. name, location, quantity)
    signature: str = ""      # Digital signature (populated in Stage 6; empty in Stage 1)
    event_id: str = field(default="")  # Content-addressable SHA256 hash or explicit ID

    def __post_init__(self) -> None:
        """
        Compute deterministic event_id if not provided.
        Design Decision:
        Content-addressable hashing ensures that identical events produce identical IDs.
        This provides natural deduplication and idempotency at the database layer.
        """
        if not self.event_id:
            # Generate deterministic SHA256 from the canonical event contents
            # (excluding signature and event_id itself)
            raw = self.canonical_content_bytes()
            computed_id = hashlib.sha256(raw).hexdigest()
            # dataclass is frozen, so use object.__setattr__ during init
            object.__setattr__(self, "event_id", computed_id)

    def canonical_content_bytes(self) -> bytes:
        """
        Returns canonical byte representation of the event content (excluding event_id and signature).
        Design Decision:
        Deterministic JSON (sorted keys, no extra whitespace) ensures hash stability
        across different operating systems and Python versions.
        """
        core_data = {
            "node_id": self.node_id,
            "counter": self.counter,
            "timestamp": round(self.timestamp, 6),  # Normalize float precision
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "operation": self.operation,
            "payload": self.payload,
        }
        return json.dumps(core_data, sort_keys=True, separators=(",", ":")).encode("utf-8")

    def to_dict(self) -> Dict[str, Any]:
        """Convert event to serializable dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Event:
        """Reconstruct event instance from dictionary."""
        return cls(
            node_id=data["node_id"],
            counter=int(data["counter"]),
            timestamp=float(data["timestamp"]),
            entity_type=data["entity_type"],
            entity_id=data["entity_id"],
            operation=data["operation"],
            payload=dict(data.get("payload", {})),
            signature=data.get("signature", ""),
            event_id=data.get("event_id", ""),
        )

    def to_json(self) -> str:
        """Serialize event to compact JSON string."""
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))

    @classmethod
    def from_json(cls, json_str: str) -> Event:
        """Deserialize event from JSON string."""
        return cls.from_dict(json.loads(json_str))

    def wire_byte_size(self) -> int:
        """
        Returns exact wire size in UTF-8 bytes for sync tracking (used in Stage 2).
        """
        return len(self.to_json().encode("utf-8"))
