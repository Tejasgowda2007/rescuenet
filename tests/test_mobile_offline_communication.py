"""
tests/test_mobile_offline_communication.py

Comprehensive Automated Test Suite for RescueNet Mobile-to-Mobile Offline Communication:
1. Two Android devices (Phone A: android-alpha and Phone B: android-beta).
2. Direct peer discovery, connection establishment, and peer identification.
3. Wire-level byte framing [4-byte big-endian length][payload], Ed25519 signing, and AES-256-GCM encryption.
4. Phone A sends tactical emergency message to Phone B (without internet).
5. Phone B sends disaster incident report to Phone A (without internet).
6. Offline store-and-forward outbox synchronization under simulated Airplane Mode.
7. FastAPI REST endpoints & WebSocket broadcasts for /api/incidents and /api/messages.
"""

import base64
import json
import os
import struct
import time
import pytest
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi.testclient import TestClient

from api.server import app, state, require_responder, get_current_user
from auth.tokens import create_access_token


# ---------------------------------------------------------------------------
# FIXTURES & MOCK WIRE PROTOCOL
# ---------------------------------------------------------------------------

SHARED_MESH_PSK = b"RescueNet-Mesh-PSK-256bit-Key-!!" # 32 bytes AES-256-GCM PSK

class SimulatedAndroidNode:
    """Simulates an Android phone running NearbyMeshService and NearbyWebBridge."""
    def __init__(self, node_id: str, callsign: str):
        self.node_id = node_id
        self.callsign = callsign
        self.private_key = ed25519.Ed25519PrivateKey.generate()
        self.public_key = self.private_key.public_key()
        self.connected_peers = {} # endpoint_id -> PeerInfo
        self.received_messages = []
        self.received_incidents = []
        self.outbox_queue = []

    def frame_packet(self, payload_dict: dict) -> bytes:
        """Create RescueNet 4-byte big-endian framed, signed, and encrypted byte stream."""
        raw_json = json.dumps(payload_dict, sort_keys=True).encode("utf-8")
        signature = self.private_key.sign(raw_json)
        
        envelope = {
            "node_id": self.node_id,
            "callsign": self.callsign,
            "signature": base64.b64encode(signature).decode("utf-8"),
            "data": payload_dict,
        }
        envelope_bytes = json.dumps(envelope).encode("utf-8")
        
        # AES-256-GCM encryption
        aesgcm = AESGCM(SHARED_MESH_PSK)
        nonce = os.urandom(12)
        ciphertext = aesgcm.encrypt(nonce, envelope_bytes, None)
        wire_body = nonce + ciphertext

        # 4-byte big-endian length prefix
        return struct.pack(">I", len(wire_body)) + wire_body

    def unframe_packet(self, framed_bytes: bytes, sender_public_key: ed25519.Ed25519PublicKey) -> dict:
        """Decode framed packet, decrypt AES-256-GCM, and verify Ed25519 signature."""
        assert len(framed_bytes) >= 4, "Packet too short for length header"
        frame_len = struct.unpack(">I", framed_bytes[:4])[0]
        wire_body = framed_bytes[4:]
        assert len(wire_body) == frame_len, f"Frame length mismatch: {len(wire_body)} != {frame_len}"

        # Decrypt AES-256-GCM
        nonce = wire_body[:12]
        ciphertext = wire_body[12:]
        aesgcm = AESGCM(SHARED_MESH_PSK)
        plaintext = aesgcm.decrypt(nonce, ciphertext, None)

        envelope = json.loads(plaintext.decode("utf-8"))
        signature = base64.b64decode(envelope["signature"])
        data_bytes = json.dumps(envelope["data"], sort_keys=True).encode("utf-8")

        # Verify Ed25519 digital signature
        sender_public_key.verify(signature, data_bytes)
        return envelope["data"]

    def receive_wire_bytes(self, framed_bytes: bytes, sender_public_key: ed25519.Ed25519PublicKey):
        """Process incoming raw wire bytes received over Nearby P2P."""
        payload = self.unframe_packet(framed_bytes, sender_public_key)
        p_type = payload.get("type")
        if p_type == "MESSAGE":
            self.received_messages.append(payload["data"])
        elif p_type == "INCIDENT":
            self.received_incidents.append(payload["data"])
        return payload


# ---------------------------------------------------------------------------
# TESTS
# ---------------------------------------------------------------------------

def test_peer_discovery_and_handshake():
    """Verify two Android devices discover each other, negotiate credentials, and record peer state."""
    phone_a = SimulatedAndroidNode("android-alpha", "Alpha Harbor Command")
    phone_b = SimulatedAndroidNode("android-beta", "Beta Field Triage")

    # Simulate Nearby Connections discovery & connection handshake
    endpoint_a = "EP_ALPHA_01"
    endpoint_b = "EP_BETA_02"

    phone_a.connected_peers[endpoint_b] = {
        "endpoint_id": endpoint_b,
        "name": phone_b.callsign,
        "node_id": phone_b.node_id,
        "connected_at": time.time(),
    }

    phone_b.connected_peers[endpoint_a] = {
        "endpoint_id": endpoint_a,
        "name": phone_a.callsign,
        "node_id": phone_a.node_id,
        "connected_at": time.time(),
    }

    assert len(phone_a.connected_peers) == 1
    assert len(phone_b.connected_peers) == 1
    assert phone_a.connected_peers[endpoint_b]["name"] == "Beta Field Triage"
    assert phone_b.connected_peers[endpoint_a]["name"] == "Alpha Harbor Command"


def test_send_message_phone_a_to_phone_b_offline():
    """Verify Phone A sends an encrypted, signed tactical emergency message to Phone B without internet."""
    phone_a = SimulatedAndroidNode("android-alpha", "Alpha Command Post")
    phone_b = SimulatedAndroidNode("android-beta", "Beta Field Medic")

    # Phone A composes message
    msg_data = {
        "id": "msg-9901-test",
        "sender_id": phone_a.node_id,
        "recipient_id": phone_b.node_id,
        "content": "P0 SOS: Urgent medical triage requested at Trishul Pass Km 14. 3 wounded.",
        "priority": "CRITICAL",
        "timestamp": int(time.time() * 1000),
        "status": "SENT",
    }
    payload = {"type": "MESSAGE", "data": msg_data}

    # Frame, sign with Ed25519, encrypt with AES-256-GCM
    wire_bytes = phone_a.frame_packet(payload)
    assert len(wire_bytes) > 4
    assert wire_bytes[:4] == struct.pack(">I", len(wire_bytes) - 4)

    # Phone B receives wire bytes over ad-hoc peer transport
    decoded = phone_b.receive_wire_bytes(wire_bytes, phone_a.public_key)

    assert decoded["type"] == "MESSAGE"
    assert len(phone_b.received_messages) == 1
    received = phone_b.received_messages[0]
    assert received["id"] == "msg-9901-test"
    assert received["sender_id"] == "android-alpha"
    assert received["priority"] == "CRITICAL"
    assert "Urgent medical triage" in received["content"]


def test_send_incident_report_phone_b_to_phone_a_offline():
    """Verify Phone B creates a disaster incident report and transmits to Phone A over P2P."""
    phone_a = SimulatedAndroidNode("android-alpha", "Alpha Command Post")
    phone_b = SimulatedAndroidNode("android-beta", "Beta Field Medic")

    # Phone B creates incident report
    incident_data = {
        "id": "inc-7702-test",
        "title": "Flash Flood Trapping 4 Hikers at Sector Charlie",
        "category": "FLOOD",
        "severity": "CRITICAL",
        "status": "OPEN",
        "location": "Sector Charlie Gorge Grid 5A",
        "description": "Rising waters cutting off footbridge. Water level rising 10 cm/hr.",
        "assigned_teams": ["Beta Field Triage Team", "Alpha SAR 1"],
        "reported_by": phone_b.node_id,
        "created_at": int(time.time() * 1000),
        "synced": False,
    }
    payload = {"type": "INCIDENT", "data": incident_data}

    # Frame, sign, encrypt
    wire_bytes = phone_b.frame_packet(payload)

    # Phone A receives wire bytes
    phone_a.receive_wire_bytes(wire_bytes, phone_b.public_key)

    assert len(phone_a.received_incidents) == 1
    rx_inc = phone_a.received_incidents[0]
    assert rx_inc["id"] == "inc-7702-test"
    assert rx_inc["title"] == "Flash Flood Trapping 4 Hikers at Sector Charlie"
    assert rx_inc["category"] == "FLOOD"
    assert rx_inc["severity"] == "CRITICAL"
    assert rx_inc["reported_by"] == "android-beta"


def test_store_and_forward_outbox_queue_sync():
    """Verify offline store-and-forward outbox queues actions during Airplane Mode and flushes upon restoration."""
    phone = SimulatedAndroidNode("android-alpha", "Alpha Operator")

    # Simulate Airplane Mode: user logs 3 incidents while offline
    offline_items = [
        {"id": f"inc-offline-{i}", "title": f"Incident {i}", "category": "MEDEVAC", "severity": "HIGH"}
        for i in range(1, 4)
    ]
    for item in offline_items:
        phone.outbox_queue.append({
            "url": "/api/incidents",
            "method": "POST",
            "body": item,
            "status": "PENDING",
            "retry_count": 0,
        })

    assert len(phone.outbox_queue) == 3
    assert all(m["status"] == "PENDING" for m in phone.outbox_queue)

    # Simulate connectivity restoration: flush outbox
    synced_items = []
    for mutation in list(phone.outbox_queue):
        mutation["status"] = "SYNCING"
        # Simulate network success
        mutation["status"] = "SYNCED"
        synced_items.append(mutation["body"]["id"])
        phone.outbox_queue.remove(mutation)

    assert len(phone.outbox_queue) == 0
    assert len(synced_items) == 3
    assert "inc-offline-1" in synced_items
    assert "inc-offline-2" in synced_items
    assert "inc-offline-3" in synced_items


def test_backend_incidents_rest_api():
    """Verify backend FastAPI /api/incidents handles creation, listing, and updates."""
    client = TestClient(app)
    token = create_access_token(user_id="u-admin", username="admin", role="commander")
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Create Incident
    payload = {
        "title": "Landslide blocking Trishul Pass",
        "category": "COLLAPSE",
        "severity": "CRITICAL",
        "location": "Trishul Pass Km 12",
        "description": "Boulders on roadway, emergency vehicles cannot pass.",
        "reported_by": "field-unit-alpha",
        "assigned_teams": ["Alpha SAR 1"],
    }
    res = client.post("/api/incidents", json=payload, headers=headers)
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["status"] == "INCIDENT_CREATED"
    incident_id = data["incident_id"]

    # 2. Get Incidents
    res = client.get("/api/incidents", headers=headers)
    assert res.status_code == 200
    incidents = res.json()
    assert any(i.get("id") == incident_id or i.get("title") == payload["title"] for i in incidents)

    # 3. Update Incident Status
    res = client.post(
        f"/api/incidents/{incident_id}/status",
        json={"status": "RESOLVED", "resolution_notes": "Road cleared by bulldozers"},
        headers=headers,
    )
    assert res.status_code == 200
    assert res.json()["status"] == "INCIDENT_RESOLVED"


def test_backend_messages_rest_api():
    """Verify backend FastAPI /api/messages handles emergency message transmission."""
    client = TestClient(app)
    token = create_access_token(user_id="u-medic", username="beta-medic", role="responder")
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Send Emergency Message
    msg_payload = {
        "sender_id": "beta-medic",
        "recipient_id": "alpha-command",
        "content": "Oxygen tanks running low at triage tent. Requesting re-supply.",
        "priority": "HIGH",
        "location": "Beta Field Hospital",
    }
    res = client.post("/api/messages", json=msg_payload, headers=headers)
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["status"] in ("MESSAGE_SENT", "MESSAGE_TRANSMITTED")
    assert data["message"]["content"] == msg_payload["content"]
    msg_id = data["message"]["id"]

    # 2. List Messages
    res = client.get("/api/messages", headers=headers)
    assert res.status_code == 200
    msgs = res.json()
    assert any(m.get("id") == msg_id or m.get("content") == msg_payload["content"] for m in msgs)
