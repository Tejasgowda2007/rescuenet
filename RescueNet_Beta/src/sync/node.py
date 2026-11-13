"""
RescueNet Node: Coordinator combining Event Store, State Projector, Crypto Keyring, and Sync Engine.

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
    compress_events,
    decompress_events,
)


class StrictSecurityError(Exception):
    """Raised when an operation violates strict production security enforcement."""
    pass


class Node:
    """
    A standalone disaster coordination node (e.g. volunteer laptop or phone).

    Design Decisions:
    1. Offline-First: All reads and writes target local SQLite immediately.
    2. Monotonic Local Counter: Continues from highest logged counter upon restart,
       guaranteeing no counter collision or equivocation.
    3. Bi-Directional Anti-Entropy: Sync is symmetrical. After one sync handshake,
       both nodes hold the exact union of each other's event histories.
    4. Cryptographic Security (Stage 6):
       - If a NodeKeyring is attached:
         * Sensitive payload fields are encrypted at rest with passphrase-derived AES-256-GCM.
         * Events are signed with Ed25519; incoming forged events are rejected.
    """

    def __init__(
        self,
        node_id: str,
        db_path: str = ":memory:",
        transport: Optional[Transport] = None,
        keyring: Optional[Any] = None,  # Optional NodeKeyring
        strict_mode: bool = False,
    ) -> None:
        self.node_id = node_id
        self.store = SQLiteEventStore(db_path)
        self.projector = StateProjector()
        self.transport = transport
        self.keyring = keyring
        self.strict_mode = strict_mode
        self.security_drop_log: List[Dict[str, Any]] = []

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

    def set_keyring(self, keyring: Any) -> None:
        """Attach cryptographic keyring for field encryption and digital signatures."""
        self.keyring = keyring

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
        Increments the node's local logical counter, encrypts sensitive fields,
        signs with private key, and appends to local SQLite.
        """
        self._local_counter += 1
        ts = timestamp if timestamp is not None else time.time()

        if self.strict_mode:
            if self.keyring is None:
                raise StrictSecurityError(
                    f"Strict security violation on node '{self.node_id}': Cannot record event without active keyring."
                )
            if self.keyring.private_key is None:
                raise StrictSecurityError(
                    f"Strict security violation on node '{self.node_id}': Cannot record event without private Ed25519 signing key."
                )
            if self.keyring.mesh_cipher is None:
                raise StrictSecurityError(
                    f"Strict security violation on node '{self.node_id}': Cannot record event without active 256-bit Mesh PSK cipher."
                )

        stored_payload = payload
        if self.keyring is not None:
            stored_payload = self.keyring.encrypt_payload(payload)

        if self.strict_mode:
            from crypto.ciphers import DEFAULT_SENSITIVE_FIELDS
            for field_name, field_val in payload.items():
                if field_name in DEFAULT_SENSITIVE_FIELDS and field_val is not None:
                    enc_val = stored_payload.get(field_name)
                    if not isinstance(enc_val, dict) or not enc_val.get("__enc__"):
                        raise StrictSecurityError(
                            f"Strict security violation on node '{self.node_id}': "
                            f"Sensitive victim field '{field_name}' failed encryption and cannot be stored in plaintext!"
                        )

        event = Event(
            node_id=self.node_id,
            counter=self._local_counter,
            timestamp=ts,
            entity_type=entity_type,
            entity_id=entity_id,
            operation=operation,
            payload=stored_payload,
        )

        if self.keyring is not None:
            event = self.keyring.sign_event(event)

        self.store.append(event)
        return event

    def get_state(self) -> Dict[str, Dict[str, Any]]:
        """
        Materialize current domain state directly from local event log.
        If keyring is attached, decrypts sensitive fields for authorized display.
        """
        all_events = self.store.get_all_events()

        if self.keyring is not None:
            decrypted_events = [
                Event(
                    node_id=e.node_id,
                    counter=e.counter,
                    timestamp=e.timestamp,
                    entity_type=e.entity_type,
                    entity_id=e.entity_id,
                    operation=e.operation,
                    payload=self.keyring.decrypt_payload(e.payload),
                    signature=e.signature,
                    event_id=e.event_id,
                )
                for e in all_events
            ]
            return self.projector.compute_state(decrypted_events)

        return self.projector.compute_state(all_events)

    def get_version_vector(self) -> Dict[str, int]:
        """Return the current local version vector {node_id: max_counter}."""
        return self.store.get_version_vector()

    def _verify_and_filter_events(self, events: List[Event]) -> List[Event]:
        """
        Drop any incoming event that fails signature verification.
        Design Decision:
        Prevents forged, unsigned, revoked, or unregistered peer updates
        from ever being written to SQLite (Fail-Closed).
        """
        if self.keyring is None:
            if self.strict_mode:
                raise StrictSecurityError(
                    f"Strict security violation on node '{self.node_id}': Cannot process sync events in unauthenticated mode."
                )
            # Unauthenticated mode (preserves Stages 1-5 & Stage 7 baseline tests)
            return events

        valid_events = []
        for ev in events:
            # Rule 1: Drop events from revoked devices
            if self.keyring.is_revoked(ev.node_id):
                self._log_security_drop(ev, "REVOKED_PEER")
                continue

            # Rule 2: Fail-Closed: Drop events from unknown / unregistered peers
            if ev.node_id not in self.keyring.trusted_peers:
                self._log_security_drop(ev, "UNKNOWN_PEER")
                continue

            # Rule 3: Fail-Closed: Drop unsigned events when keyring is active
            if not ev.signature:
                self._log_security_drop(ev, "MISSING_SIGNATURE")
                continue

            # Rule 4: Verify Ed25519 digital signature
            if not self.keyring.verify_event(ev):
                self._log_security_drop(ev, "INVALID_SIGNATURE")
                continue

            valid_events.append(ev)
        return valid_events

    def _log_security_drop(self, event: Event, reason: str) -> None:
        """Record dropped event telemetry for security audit log."""
        self.security_drop_log.append({
            "event_id": event.event_id,
            "node_id": event.node_id,
            "counter": event.counter,
            "reason": reason,
            "timestamp": time.time(),
        })

    def sync_with(self, peer_id: str) -> SyncStats:
        """
        Execute bi-directional anti-entropy synchronization with a peer node.

        Protocol Flow:
        1. Initiator (Self) -> SYNC_REQUEST(V_self) -> Responder (Peer)
        2. Responder replies with SYNC_RESPONSE(V_peer, missing_events_for_self)
        3. Initiator verifies signatures, ingests missing_events, then sends SYNC_DELTA.
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

        # Step 2: Verify and ingest events sent from peer
        peer_vv = dict(resp_msg.payload.get("version_vector", {}))
        events_from_peer_dicts = decompress_events(resp_msg.payload)
        events_from_peer = [Event.from_dict(d) for d in events_from_peer_dicts]
        valid_events = self._verify_and_filter_events(events_from_peer)

        if valid_events:
            self.store.append_many(valid_events)
            events_received_count = len(valid_events)

        # Step 3: Determine what events peer is missing based on peer's version vector
        events_for_peer = self.store.get_events_since(peer_vv)
        if events_for_peer:
            delta_msg = TransportMessage(
                sender_id=self.node_id,
                recipient_id=peer_id,
                message_type=MSG_SYNC_DELTA,
                payload={"events_z": compress_events([e.to_dict() for e in events_for_peer])},
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
            peer_vv = dict(message.payload.get("version_vector", {}))
            missing_for_peer = self.store.get_events_since(peer_vv)
            my_vv = self.get_version_vector()

            return TransportMessage(
                sender_id=self.node_id,
                recipient_id=message.sender_id,
                message_type=MSG_SYNC_RESPONSE,
                payload={
                    "version_vector": my_vv,
                    "events_z": compress_events([e.to_dict() for e in missing_for_peer]),
                },
            )

        elif message.message_type == MSG_SYNC_DELTA:
            incoming_event_dicts = decompress_events(message.payload)
            incoming_events = [Event.from_dict(d) for d in incoming_event_dicts]
            valid_events = self._verify_and_filter_events(incoming_events)
            ingested_count = self.store.append_many(valid_events)

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
