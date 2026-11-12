"""
Sync Protocol Message Constants and Session Statistics.
"""

from __future__ import annotations
import base64
import json
import zlib
from dataclasses import dataclass

def compress_events(events_list):
    """Compress a list of event dicts into a base64 zlib string for weak links."""
    raw = json.dumps(events_list, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return base64.b64encode(zlib.compress(raw, level=9)).decode("ascii")

def decompress_events(payload):
    """Accept either 'events' (list) or 'events_z' (compressed str)."""
    if "events_z" in payload and payload.get("events_z"):
        raw = zlib.decompress(base64.b64decode(payload["events_z"]))
        return json.loads(raw.decode("utf-8"))
    return payload.get("events", [])

# Protocol Message Types
MSG_SYNC_REQUEST = "SYNC_REQUEST"    # Step 1: Initiator sends local Version Vector
MSG_SYNC_RESPONSE = "SYNC_RESPONSE"  # Step 2: Responder sends its Version Vector + missing events
MSG_SYNC_DELTA = "SYNC_DELTA"        # Step 3: Initiator sends events responder is missing
MSG_SYNC_ACK = "SYNC_ACK"            # Step 4: Responder acknowledges ingestion


@dataclass(frozen=True)
class SyncStats:
    """
    Detailed telemetry returned after every sync encounter.

    Design Decision:
    Requirement 4 mandates tracking and reporting bytes sent.
    SyncStats provides full accounting of network overhead, payload size,
    and event counts exchanged between two nodes.
    """
    initiator_id: str
    peer_id: str
    success: bool
    events_sent: int
    events_received: int
    bytes_sent: int
    bytes_received: int
    total_bytes: int
    error: str = ""

    def summary(self) -> str:
        """User-friendly summary string of sync outcome."""
        if not self.success:
            return f"Sync failed with {self.peer_id}: {self.error}"
        return (
            f"Synced with {self.peer_id} | "
            f"Sent: {self.events_sent} ev ({self.bytes_sent} B), "
            f"Recv: {self.events_received} ev ({self.bytes_received} B), "
            f"Total Wire: {self.total_bytes} B"
        )
