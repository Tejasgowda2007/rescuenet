"""
RescueNet Node: Coordinator combining Event Store, State Projector, and Sync Engine.

Each physical or simulated device is represented by an instance of Node.
Volunteers interact with this node locally with zero internet.
When in range of a peer, `sync_with(peer_id)` runs the anti-entropy protocol.
"""

from __future__ import annotations
import time
from typing import Dict, Any, List, Optional
from events.event import Event
from storage.sqlite_store import SQLiteEventStore
from storage.projector import StateProjector
from transport.base import Transport, TransportMessage
from .messages import (
    SyncStats,
    MSG_SYNC_REQUEST,
    MSG_SYNC_RESPONSE,
    MSG_SYNC_DELTA,
    MSG_SYNC_ACK,
)


class Node:
    """
    A standalone disaster coordination node (e.g. volunteer laptop or phone).

    Design Decisions:
    1. Offline-First: All reads and writes target local SQLite immediately.
    2. Monotonic Local Counter: Continues from highest logged counter upon restart,
       guaranteeing no counter collision or equivocation.
    3. Bi-Directional Anti-Entropy: Sync is symmetrical. After one sync handshake,
       both nodes hold the exact union of each other's event histories.
    """

    def __init__(
        self,
        node_id: str,
        db_path: str = ":memory:",
        transport: Optional[Transport] = None,
    ) -> None:
        self.node_id = node_id
        self.store = SQLiteEventStore(db_path)
        self.projector = StateProjector()
        self.transport = transport

        # Initialize local counter from persistent store (resilient to restarts)
        existing_vv = self.store.get_version_vector()
        self._local_counter = existing_vv.get(self.node_id, 0)

        # Register message listener with transport if provided
        if self.transport is not None:
            self.transport.register_node(self.node_id, self.handle_transport_message)

    def attach_transport(self, transport: Transport) -> None:
        """Attach or update the network transport layer."""
        self.transport = transport
        self.transport.register_node(self.node_id, self.handle_transport_message)

    def record_event(
        self,
        entity_type: str,
        entity_id: str,
        operation: str,
        payload: Dict[str, Any],
        timestamp: Optional[float] = None,
    ) -> Event:
        """
        Record a local action taken by the volunteer with NO internet.
        Increments the node's local logical counter and appends to local SQLite.
        """
        self._local_counter += 1
        ts = timestamp if timestamp is not None else time.time()

        event = Event(
            node_id=self.node_id,
            counter=self._local_counter,
            timestamp=ts,
            entity_type=entity_type,
            entity_id=entity_id,
            operation=operation,
            payload=payload,
        )

        self.store.append(event)
        return event

    def get_state(self) -> Dict[str, Dict[str, Any]]:
        """Materialize current domain state directly from local event log."""
        all_events = self.store.get_all_events()
        return self.projector.compute_state(all_events)

    def get_version_vector(self) -> Dict[str, int]:
        """Return the current local version vector {node_id: max_counter}."""
        return self.store.get_version_vector()

    def sync_with(self, peer_id: str) -> SyncStats:
        """
        Execute bi-directional anti-entropy synchronization with a peer node.

        Protocol Flow:
        1. Initiator (Self) -> SYNC_REQUEST(V_self) -> Responder (Peer)
        2. Responder replies with SYNC_RESPONSE(V_peer, missing_events_for_self)
        3. Initiator ingests missing_events, then checks what responder is missing:
           Initiator -> SYNC_DELTA(missing_events_for_peer) -> Responder
        4. Responder acknowledges with SYNC_ACK.
        """
        if self.transport is None:
            return SyncStats(
                initiator_id=self.node_id,
                peer_id=peer_id,
                success=False,
                events_sent=0,
                events_received=0,
                bytes_sent=0,
                bytes_received=0,
                total_bytes=0,
                error="No transport attached to node",
            )

        bytes_sent = 0
        bytes_received = 0
        events_sent_count = 0
        events_received_count = 0

        # Step 1: Send our local version vector to peer
        my_vv = self.get_version_vector()
        req_msg = TransportMessage(
            sender_id=self.node_id,
            recipient_id=peer_id,
            message_type=MSG_SYNC_REQUEST,
            payload={"version_vector": my_vv},
        )
        bytes_sent += req_msg.wire_byte_size()

        resp_msg = self.transport.send(req_msg)
        if resp_msg is None:
            return SyncStats(
                initiator_id=self.node_id,
                peer_id=peer_id,
                success=False,
                events_sent=0,
                events_received=0,
                bytes_sent=bytes_sent,
                bytes_received=0,
                total_bytes=bytes_sent,
                error="Peer unreachable (network partition or peer offline)",
            )

        bytes_received += resp_msg.wire_byte_size()

        # Step 2: Ingest events sent from peer
        peer_vv = dict(resp_msg.payload.get("version_vector", {}))
        events_from_peer_dicts = resp_msg.payload.get("events", [])
        events_from_peer = [Event.from_dict(d) for d in events_from_peer_dicts]

        if events_from_peer:
            self.store.append_many(events_from_peer)
            events_received_count = len(events_from_peer)

        # Step 3: Determine what events peer is missing based on peer's version vector
        events_for_peer = self.store.get_events_since(peer_vv)
        if events_for_peer:
            delta_msg = TransportMessage(
                sender_id=self.node_id,
                recipient_id=peer_id,
                message_type=MSG_SYNC_DELTA,
                payload={"events": [e.to_dict() for e in events_for_peer]},
            )
            bytes_sent += delta_msg.wire_byte_size()
            events_sent_count = len(events_for_peer)

            ack_msg = self.transport.send(delta_msg)
            if ack_msg is not None:
                bytes_received += ack_msg.wire_byte_size()

        total_wire_bytes = bytes_sent + bytes_received

        return SyncStats(
            initiator_id=self.node_id,
            peer_id=peer_id,
            success=True,
            events_sent=events_sent_count,
            events_received=events_received_count,
            bytes_sent=bytes_sent,
            bytes_received=bytes_received,
            total_bytes=total_wire_bytes,
        )

    def handle_transport_message(self, message: TransportMessage) -> Optional[TransportMessage]:
        """
        Server-side handler called by transport when a peer sends a message to this node.
        """
        if message.message_type == MSG_SYNC_REQUEST:
            # Peer wants to sync with us:
            # 1. Inspect peer's version vector
            peer_vv = dict(message.payload.get("version_vector", {}))
            # 2. Extract events peer has not seen
            missing_for_peer = self.store.get_events_since(peer_vv)
            # 3. Read our own version vector
            my_vv = self.get_version_vector()

            return TransportMessage(
                sender_id=self.node_id,
                recipient_id=message.sender_id,
                message_type=MSG_SYNC_RESPONSE,
                payload={
                    "version_vector": my_vv,
                    "events": [e.to_dict() for e in missing_for_peer],
                },
            )

        elif message.message_type == MSG_SYNC_DELTA:
            # Peer is delivering events that we were missing
            incoming_event_dicts = message.payload.get("events", [])
            incoming_events = [Event.from_dict(d) for d in incoming_event_dicts]
            ingested_count = self.store.append_many(incoming_events)

            return TransportMessage(
                sender_id=self.node_id,
                recipient_id=message.sender_id,
                message_type=MSG_SYNC_ACK,
                payload={"ingested_count": ingested_count},
            )

        return None

    def close(self) -> None:
        """Close SQLite database and unregister from transport."""
        if self.transport is not None:
            self.transport.unregister_node(self.node_id)
        self.store.close()
