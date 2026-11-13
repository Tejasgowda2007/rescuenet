"""
Unit and Integration Tests for Stage 6:
Field-Level Encryption at Rest, Ed25519 Event Signing, and Seized Device Protection.
"""

import os
import json
import sqlite3
import pytest
from crypto.ciphers import FieldEncryptor, CryptoError
from crypto.signatures import Signer
from crypto.keyring import NodeKeyring
from sync.node import Node
from transport.in_memory import InMemoryTransport
from events.event import Event


def test_field_encryption_aes_gcm_roundtrip():
    """Verify AES-256-GCM field encryption, correct decryption, and wrong passphrase rejection."""
    passphrase = "SecretPassphrase2026!"
    salt = os.urandom(16)
    original_data = "Patient requires daily dialysis treatment"

    envelope = FieldEncryptor.encrypt_value(original_data, passphrase, salt)
    assert envelope["__enc__"] is True
    assert "nonce" in envelope
    assert "data" in envelope

    # Decrypt with correct passphrase
    decrypted = FieldEncryptor.decrypt_value(envelope, passphrase, salt)
    assert decrypted == original_data

    # Decrypt with wrong passphrase -> must raise CryptoError
    with pytest.raises(CryptoError):
        FieldEncryptor.decrypt_value(envelope, "WrongPassphrase999", salt)

    # Tamper with ciphertext -> must fail GCM authentication tag
    tampered_envelope = dict(envelope)
    # Corrupt one hex byte
    tampered_envelope["data"] = "ff" + envelope["data"][2:]
    with pytest.raises(CryptoError):
        FieldEncryptor.decrypt_value(tampered_envelope, passphrase, salt)


def test_ed25519_event_signing_and_tamper_detection():
    """Verify Ed25519 digital signature generation and tamper detection."""
    priv, pub_hex = Signer.generate_keypair()

    event = Event(
        node_id="station-alpha",
        counter=1,
        timestamp=100.0,
        entity_type="shelter",
        entity_id="sh-1",
        operation="CREATE",
        payload={"name": "Depot"},
    )

    signed_event = Signer.sign_event(event, priv)
    assert len(signed_event.signature) == 128  # 64 bytes in hex
    assert Signer.verify_event(signed_event, pub_hex) is True

    # Tamper with event counter
    tampered_event = Event(
        node_id=signed_event.node_id,
        counter=999,  # Changed!
        timestamp=signed_event.timestamp,
        entity_type=signed_event.entity_type,
        entity_id=signed_event.entity_id,
        operation=signed_event.operation,
        payload=signed_event.payload,
        signature=signed_event.signature,
        event_id=signed_event.event_id,
    )
    assert Signer.verify_event(tampered_event, pub_hex) is False


def test_node_rejects_forged_peer_events():
    """
    Test that an attacker attempting to forge an update from a trusted peer is rejected.
    """
    transport = InMemoryTransport()

    # Node Alpha and Node Beta set up keyrings and trust each other's public keys
    kr_alpha = NodeKeyring("node-A", passphrase="alpha_passphrase")
    kr_beta = NodeKeyring("node-B", passphrase="beta_passphrase")

    kr_alpha.register_peer("node-B", kr_beta.public_key_hex)
    kr_beta.register_peer("node-A", kr_alpha.public_key_hex)

    node_a = Node("node-A", ":memory:", transport, keyring=kr_alpha)
    node_b = Node("node-B", ":memory:", transport, keyring=kr_beta)

    # Node B records legitimate signed event
    node_b.record_event("need", "need-water", "CREATE", {"liters": 500})
    node_a.sync_with("node-B")
    assert node_a.store.count() == 1

    # Attacker tries to impersonate Node B with a forged event signed by attacker's rogue key
    rogue_priv, rogue_pub = Signer.generate_keypair()
    forged_raw = Event(
        node_id="node-B",  # Claims to be Node B!
        counter=2,
        timestamp=200.0,
        entity_type="shelter",
        entity_id="fake-shelter",
        operation="CREATE",
        payload={"name": "Evacuation Trap"},
    )
    forged_signed = Signer.sign_event(forged_raw, rogue_priv)

    # Deliver forged event to Node A via transport
    from transport.base import TransportMessage
    from sync.messages import MSG_SYNC_DELTA

    delta_msg = TransportMessage(
        sender_id="attacker",
        recipient_id="node-A",
        message_type=MSG_SYNC_DELTA,
        payload={"events": [forged_signed.to_dict()]},
    )
    transport.send(delta_msg)

    # Node A must have rejected the forged event
    assert node_a.store.count() == 1
    assert node_a.store.get_event(forged_signed.event_id) is None

    node_a.close()
    node_b.close()


def test_seized_device_at_rest_protection():
    """
    Demonstrate that an attacker with raw SQLite file access cannot read
    sensitive victim medical or personal data without the passphrase.
    """
    db_file = "test_seized_device.db"
    if os.path.exists(db_file):
        os.remove(db_file)

    passphrase = "VolunteerFieldPassphrase2026!"
    keyring = NodeKeyring("medic-laptop", passphrase=passphrase)
    node = Node("medic-laptop", db_file, keyring=keyring)

    # Log highly sensitive disaster medical record
    node.record_event(
        entity_type="person",
        entity_id="patient-101",
        operation="CREATE",
        payload={
            "name": "Sarah Connor",
            "condition": "Severe internal hemorrhaging",
            "last_seen": "Collapsed near Chemical Plant Sector 7",
            "phone": "+1-555-0199",
            "triage_category": "IMMEDIATE",
        },
    )

    node.close()

    # --- SIMULATE ATTACKER / PHYSICAL SEIZURE ---
    # Attacker connects directly to the raw SQLite file without the Python app or passphrase
    raw_conn = sqlite3.connect(db_file)
    cur = raw_conn.cursor()
    cur.execute("SELECT payload_json FROM events WHERE entity_id = 'patient-101'")
    raw_payload_str = cur.fetchone()[0]
    raw_conn.close()

    # Verify that raw database contains NO cleartext sensitive strings!
    assert "Sarah Connor" not in raw_payload_str
    assert "Severe internal hemorrhaging" not in raw_payload_str
    assert "Chemical Plant" not in raw_payload_str
    assert "+1-555-0199" not in raw_payload_str

    raw_data = json.loads(raw_payload_str)
    # The sensitive fields must be encrypted envelopes
    assert raw_data["name"]["__enc__"] is True
    assert raw_data["condition"]["__enc__"] is True
    # Non-sensitive triage category remains unencrypted for query filtering
    assert raw_data["triage_category"] == "IMMEDIATE"

    # --- SIMULATE AUTHORIZED RESCUE COORDINATOR UNLOCK ---
    # Volunteer unlocks device with valid passphrase
    recovery_keyring = NodeKeyring(
        "medic-laptop",
        passphrase=passphrase,
        salt=keyring.salt,
        private_key=keyring.private_key,
        public_key_hex=keyring.public_key_hex,
    )
    recovered_node = Node("medic-laptop", db_file, keyring=recovery_keyring)
    state = recovered_node.get_state()
    patient = state["person"]["patient-101"]

    # Cleartext is perfectly restored for authorized personnel!
    assert patient["name"] == "Sarah Connor"
    assert patient["condition"] == "Severe internal hemorrhaging"
    assert patient["last_seen"] == "Collapsed near Chemical Plant Sector 7"

    recovered_node.close()
    if os.path.exists(db_file):
        os.remove(db_file)
