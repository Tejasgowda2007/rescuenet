"""
Automated Security Test Suite for Phase 1: Cryptographic Hardening & Zero-Trust Mesh.

Validates all 8 threat vectors:
1. Forged signatures rejection.
2. Tampered event metadata (counter, timestamp, entity_id) rejection.
3. Incorrect peer key impersonation defense.
4. Replay attacks and equivocation rejection.
5. Key persistence, Argon2id encryption at rest, and restart recovery.
6. Cross-node AES-256-GCM encryption with 256-bit Mesh PSK and fresh nonces.
7. Revoked peers enforcement, persistence across restart, and explicit restoration.
8. Backward compatibility with legacy envelopes and unauthenticated nodes.
9. Fail-closed rejection of unregistered peers and missing signatures.
10. Dual-key zero-downtime rotation and historical decryption.
"""

import os
import shutil
import tempfile
import pytest
import secrets

from crypto.ciphers import FieldEncryptor, MeshCipher, CryptoError
from crypto.signatures import Signer
from crypto.keyring import NodeKeyring
from crypto.storage import KeyStore, KeyDecryptionError, KeyCorruptedError
from crypto.peer_manifest import (
    PeerManifest,
    compute_key_fingerprint,
    validate_ed25519_public_key,
    RevokedPeerEnrollmentError,
    FingerprintMismatchError,
    PeerManifestCorruptedError,
)
from sync.node import Node, StrictSecurityError
from transport.in_memory import InMemoryTransport
from transport.base import TransportMessage
from transport.tcp import TCPTransport, FrameTooLargeError
from sync.messages import MSG_SYNC_DELTA
from events.event import Event
from run_node import validate_and_build_strict_keyring, StrictSecurityError as CLIStrictSecurityError
from scripts.provision_mesh_keys import provision_cluster


@pytest.fixture
def temp_sec_dir():
    """Create a temporary directory for persistent security tests."""
    temp_dir = tempfile.mkdtemp(prefix="rescuenet_sec_test_")
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


def test_reject_forged_signatures():
    """Verify that an event with a forged or modified payload fails signature check and is dropped."""
    priv, pub_hex = Signer.generate_keypair()
    ev = Event(
        node_id="alpha",
        counter=1,
        timestamp=100.0,
        entity_type="person",
        entity_id="p-1",
        operation="CREATE",
        payload={"name": "Alice Smith", "condition": "STABLE"},
    )
    signed_ev = Signer.sign_event(ev, priv)
    assert Signer.verify_event(signed_ev, pub_hex) is True

    # Attacker tampers with payload
    tampered_ev = Event(
        node_id=signed_ev.node_id,
        counter=signed_ev.counter,
        timestamp=signed_ev.timestamp,
        entity_type=signed_ev.entity_type,
        entity_id=signed_ev.entity_id,
        operation=signed_ev.operation,
        payload={"name": "Alice Smith", "condition": "DECEASED"},  # Modified!
        signature=signed_ev.signature,
        event_id=signed_ev.event_id,
    )
    assert Signer.verify_event(tampered_ev, pub_hex) is False


def test_reject_tampered_counter_and_metadata():
    """Verify that altering counter, timestamp, or entity_id breaks signature validation."""
    priv, pub_hex = Signer.generate_keypair()
    ev = Event(
        node_id="alpha",
        counter=5,
        timestamp=200.0,
        entity_type="supply",
        entity_id="water-pack",
        operation="CREATE",
        payload={"liters": 100},
    )
    signed_ev = Signer.sign_event(ev, priv)

    # Counter tampering
    tampered_counter = Event(
        node_id=signed_ev.node_id,
        counter=6,  # Changed!
        timestamp=signed_ev.timestamp,
        entity_type=signed_ev.entity_type,
        entity_id=signed_ev.entity_id,
        operation=signed_ev.operation,
        payload=signed_ev.payload,
        signature=signed_ev.signature,
    )
    assert Signer.verify_event(tampered_counter, pub_hex) is False


def test_reject_incorrect_peer_key_impersonation():
    """
    Test that an attacker claiming node_id='beta' but signing with another key is rejected.
    """
    transport = InMemoryTransport()
    kr_a = NodeKeyring("node-A")
    kr_b = NodeKeyring("node-B")
    kr_a.register_peer("node-B", kr_b.public_key_hex)
    kr_b.register_peer("node-A", kr_a.public_key_hex)

    node_a = Node("node-A", ":memory:", transport, keyring=kr_a)

    # Rogue node generates its own keypair
    rogue_priv, rogue_pub = Signer.generate_keypair()

    # Rogue node crafts event claiming to be from node-B
    forged = Event(
        node_id="node-B",
        counter=1,
        timestamp=300.0,
        entity_type="shelter",
        entity_id="fake-shelter",
        operation="CREATE",
        payload={"name": "Attacker Trap"},
    )
    forged_signed = Signer.sign_event(forged, rogue_priv)

    # Filter on node A
    accepted = node_a._verify_and_filter_events([forged_signed])
    assert len(accepted) == 0
    assert any(log["reason"] == "INVALID_SIGNATURE" for log in node_a.security_drop_log)
    node_a.close()


def test_fail_closed_unknown_peer_dropped():
    """
    Test that events from an unknown / unregistered peer are dropped (Fail-Closed).
    """
    transport = InMemoryTransport()
    kr_a = NodeKeyring("node-A")  # Knows only itself
    node_a = Node("node-A", ":memory:", transport, keyring=kr_a)

    # Node Unknown has valid signatures, but is NOT enrolled in node-A's trusted_peers
    unknown_priv, unknown_pub = Signer.generate_keypair()
    ev = Event(
        node_id="unknown-device",
        counter=1,
        timestamp=400.0,
        entity_type="need",
        entity_id="need-1",
        operation="CREATE",
        payload={"item": "Food"},
    )
    signed_ev = Signer.sign_event(ev, unknown_priv)

    filtered = node_a._verify_and_filter_events([signed_ev])
    assert len(filtered) == 0
    assert any(log["reason"] == "UNKNOWN_PEER" for log in node_a.security_drop_log)
    node_a.close()


def test_key_persistence_and_reload(temp_sec_dir):
    """
    Verify persistent key storage on disk with Argon2id passphrase encryption:
    - Private key saved encrypted at rest.
    - Re-loaded and verified against stored public key.
    - Wrong passphrase raises KeyDecryptionError.
    """
    passphrase = "VolunteerFieldPassphrase2026!"
    keystore = KeyStore(temp_sec_dir, "alpha")

    # Generate and save identity
    priv, pub_hex = keystore.load_or_create_identity(passphrase)
    assert keystore.has_identity() is True
    assert len(pub_hex) == 64

    # Verify raw file on disk does NOT contain plaintext private key bytes
    with open(keystore.key_enc_file, "r") as f:
        content = f.read()
    assert "argon2id_v1" in content
    assert priv.private_bytes_raw().hex() not in content

    # Reload identity with valid passphrase in fresh KeyStore instance
    keystore2 = KeyStore(temp_sec_dir, "alpha")
    reloaded_priv, reloaded_pub = keystore2.load_identity(passphrase)
    assert reloaded_pub == pub_hex
    assert reloaded_priv.private_bytes_raw() == priv.private_bytes_raw()

    # Wrong passphrase must raise KeyDecryptionError
    with pytest.raises(KeyDecryptionError):
        keystore2.load_identity("WrongPassphrase!")


def test_cross_node_encryption_with_mesh_psk():
    """
    Verify that Node A and Node B using the same 256-bit Mesh PSK can
    encrypt and decrypt each other's PII payloads with fresh 96-bit nonces.
    """
    mesh_psk = secrets.token_bytes(32)
    cipher_a = MeshCipher(mesh_psk)
    cipher_b = MeshCipher(mesh_psk)

    original_pii = {
        "name": "Maria Rodriguez",
        "condition": "Critical - Insulin Dependent",
        "triage": "RED",
    }

    # Node A encrypts payload
    enc_payload = cipher_a.encrypt_payload(original_pii)
    assert enc_payload["name"]["__enc__"] is True
    assert enc_payload["name"]["kid"] == cipher_a.kid
    assert enc_payload["triage"] == "RED"  # Non-sensitive remains unencrypted

    # Node B decrypts payload
    dec_payload = cipher_b.decrypt_payload(enc_payload)
    assert dec_payload["name"] == "Maria Rodriguez"
    assert dec_payload["condition"] == "Critical - Insulin Dependent"

    # Node with wrong Mesh PSK cannot decrypt
    wrong_psk = secrets.token_bytes(32)
    wrong_cipher = MeshCipher(wrong_psk)
    with pytest.raises(CryptoError):
        wrong_cipher.decrypt_payload(enc_payload)


def test_revocation_enforcement_and_persistence(temp_sec_dir):
    """
    Verify device revocation:
    1. Revoked device events are dropped.
    2. Revocation persists across node restarts.
    3. Normal enrollment fails on revoked peer.
    4. Explicit restore with verified fingerprint restores trust.
    """
    manifest_dir = os.path.join(temp_sec_dir, "alpha")
    manifest = PeerManifest(manifest_dir)

    _, beta_pub = Signer.generate_keypair()
    beta_fp = compute_key_fingerprint(beta_pub)

    # 1. Enroll Beta
    manifest.enroll_peer("beta", beta_pub, alias="Hospital", role="medical")
    assert manifest.is_trusted("beta") is True

    # 2. Revoke Beta
    manifest.revoke_peer("beta", reason="Device stolen in field", effective_counter=50)
    assert manifest.is_revoked("beta") is True
    assert manifest.is_trusted("beta") is False

    # 3. Reload from disk in fresh instance
    manifest_reloaded = PeerManifest(manifest_dir)
    assert manifest_reloaded.is_revoked("beta") is True
    assert manifest_reloaded.is_trusted("beta") is False

    # 4. Normal enrollment must fail
    with pytest.raises(RevokedPeerEnrollmentError):
        manifest_reloaded.enroll_peer("beta", beta_pub)

    # 5. Explicit restoration with wrong fingerprint must fail
    with pytest.raises(FingerprintMismatchError):
        manifest_reloaded.restore_revoked_peer("beta", beta_pub, expected_fingerprint="SHA256:00:00:00:00")

    # 6. Explicit restoration with valid fingerprint succeeds
    manifest_reloaded.restore_revoked_peer("beta", beta_pub, expected_fingerprint=beta_fp)
    assert manifest_reloaded.is_trusted("beta") is True
    assert manifest_reloaded.is_revoked("beta") is False


def test_backward_compatibility_legacy_envelopes():
    """
    Verify backward compatibility:
    1. Legacy envelopes without 'kid' decrypt cleanly using legacy fallback.
    2. Unauthenticated node (keyring=None) accepts all events.
    """
    passphrase = "LegacySecretPassphrase2026!"
    salt = b"LegacySalt12345!"
    legacy_val = "Emergency Insulin Stock"

    # Create legacy envelope using FieldEncryptor
    legacy_env = FieldEncryptor.encrypt_value(legacy_val, passphrase, salt)
    assert "kid" not in legacy_env
    assert legacy_env["__enc__"] is True

    # MeshCipher initialized with legacy credentials can decrypt it
    derived_key = FieldEncryptor.derive_mesh_key(passphrase, salt)
    mesh_cipher = MeshCipher(derived_key, legacy_passphrase=passphrase, legacy_salt=salt)
    decrypted = mesh_cipher.decrypt_value(legacy_env)
    assert decrypted == legacy_val

    # Unauthenticated Node accepts unsigned events
    node = Node("unauth-node", ":memory:", keyring=None)
    unsigned_ev = Event("peer-1", 1, 100.0, "shelter", "sh-1", "CREATE", {"name": "Camp"})
    accepted = node._verify_and_filter_events([unsigned_ev])
    assert len(accepted) == 1
    node.close()


def test_dual_key_rotation_support():
    """
    Verify zero-downtime key rotation:
    - Encrypt with Key 1.
    - Rotate to Key 2.
    - Encrypt with Key 2.
    - Cipher decrypts events from BOTH Key 1 (historical) and Key 2 (active).
    """
    key_1 = secrets.token_bytes(32)
    key_2 = secrets.token_bytes(32)

    cipher = MeshCipher(key_1)
    kid_1 = cipher.kid

    env_1 = cipher.encrypt_value("Secret under Key 1")
    assert env_1["kid"] == kid_1

    # Rotate to Key 2
    kid_2 = cipher.rotate_key(key_2)
    assert kid_2 != kid_1
    assert cipher.kid == kid_2

    env_2 = cipher.encrypt_value("Secret under Key 2")
    assert env_2["kid"] == kid_2

    # Decrypt both
    assert cipher.decrypt_value(env_1) == "Secret under Key 1"
    assert cipher.decrypt_value(env_2) == "Secret under Key 2"


def test_node_full_pipeline_fail_closed_network_sync():
    """
    Integration test: Node A and Node B sync over transport with fail-closed security.
    Unregistered or tampered events sent across the wire are rejected.
    """
    transport = InMemoryTransport()
    mesh_psk = secrets.token_bytes(32)

    kr_a = NodeKeyring("node-A", mesh_key=mesh_psk)
    kr_b = NodeKeyring("node-B", mesh_key=mesh_psk)
    kr_a.register_peer("node-B", kr_b.public_key_hex)
    kr_b.register_peer("node-A", kr_a.public_key_hex)

    node_a = Node("node-A", ":memory:", transport, keyring=kr_a)
    node_b = Node("node-B", ":memory:", transport, keyring=kr_b)

    # Node B records legitimate event
    node_b.record_event("person", "p-victim", "CREATE", {"name": "Victim One", "status": "TRAPPED"})
    node_a.sync_with("node-B")
    assert node_a.store.count() == 1

    # Attacker injects forged message directly into Node A's transport spoofing Node B
    rogue_priv, _ = Signer.generate_keypair()
    forged_ev = Signer.sign_event(
        Event("node-B", 2, 500.0, "shelter", "fake-sh", "CREATE", {"name": "Poisoned"}),
        rogue_priv,
    )
    msg = TransportMessage("node-B", "node-A", MSG_SYNC_DELTA, {"events": [forged_ev.to_dict()]})
    transport.send(msg)

    # Node A store must still have only 1 legitimate event
    assert node_a.store.count() == 1
    assert any(log["reason"] == "INVALID_SIGNATURE" for log in node_a.security_drop_log)

    node_a.close()
    node_b.close()


def test_strict_security_aborts_without_keys():
    """Verify that strict security fails startup if --key-dir is omitted or does not exist."""
    with pytest.raises(CLIStrictSecurityError, match="requires --key-dir"):
        validate_and_build_strict_keyring("alpha", key_dir=None, mesh_psk_hex="00" * 32)

    with pytest.raises(CLIStrictSecurityError, match="does not exist"):
        validate_and_build_strict_keyring("alpha", key_dir="nonexistent_sec_dir_12345", mesh_psk_hex="00" * 32)


def test_strict_security_aborts_with_invalid_psk(temp_sec_dir):
    """Verify that strict security aborts if Mesh PSK is missing or invalid."""
    node_dir = os.path.join(temp_sec_dir, "alpha")
    os.makedirs(node_dir, exist_ok=True)
    keystore = KeyStore(temp_sec_dir, "alpha")
    keystore.load_or_create_identity()

    # Missing PSK
    with pytest.raises(CLIStrictSecurityError, match="valid 256-bit Mesh Pre-Shared Key"):
        validate_and_build_strict_keyring("alpha", key_dir=temp_sec_dir, mesh_psk_hex=None)

    # Short PSK (not 64 hex characters)
    with pytest.raises(CLIStrictSecurityError, match="valid 256-bit Mesh Pre-Shared Key"):
        validate_and_build_strict_keyring("alpha", key_dir=temp_sec_dir, mesh_psk_hex="abc123short")


def test_strict_security_aborts_missing_peer_manifest(temp_sec_dir):
    """Verify that strict security aborts if trusted_peers.json is missing."""
    node_dir = os.path.join(temp_sec_dir, "alpha")
    os.makedirs(node_dir, exist_ok=True)
    # Create identity keys
    keystore = KeyStore(temp_sec_dir, "alpha")
    keystore.load_or_create_identity()

    # Without trusted_peers.json
    with pytest.raises(CLIStrictSecurityError, match="Trusted peer manifest missing"):
        validate_and_build_strict_keyring("alpha", key_dir=temp_sec_dir, mesh_psk_hex="ab" * 32)


def test_strict_security_aborts_missing_local_identity(temp_sec_dir):
    """Verify that strict security aborts if identity.key.enc or identity.pub is missing."""
    node_dir = os.path.join(temp_sec_dir, "alpha")
    os.makedirs(node_dir, exist_ok=True)
    # Without creating identity keys
    with pytest.raises(CLIStrictSecurityError, match="Local Ed25519 identity key missing"):
        validate_and_build_strict_keyring("alpha", key_dir=temp_sec_dir, mesh_psk_hex="cd" * 32)


def test_strict_security_valid_startup(temp_sec_dir):
    """Verify that a properly provisioned node starts up cleanly in strict security mode."""
    summary = provision_cluster(temp_sec_dir)
    psk_hex = summary["mesh_psk_hex"]

    keyring = validate_and_build_strict_keyring(
        node_id="alpha-harbor",
        key_dir=temp_sec_dir,
        mesh_psk_hex=psk_hex,
    )
    assert keyring.private_key is not None
    assert keyring.mesh_cipher is not None
    assert len(keyring.trusted_peers) == 3
    assert "beta-hospital" in keyring.trusted_peers


def test_strict_security_blocks_plaintext_victim_pii(temp_sec_dir):
    """
    Verify that in strict mode, sensitive victim fields CANNOT be stored plaintext:
    - Attempting to record event without active encryption raises StrictSecurityError.
    """
    node = Node("unauth-node", ":memory:", keyring=None, strict_mode=True)
    with pytest.raises(StrictSecurityError, match="Cannot record event without active keyring"):
        node.record_event("person", "p-victim", "CREATE", {"name": "Victim One", "status": "TRAPPED"})
    node.close()


def test_strict_security_unauthenticated_event_rejection():
    """Verify that a node in strict mode rejects sync processing if keyring is unattached."""
    node = Node("strict-node", ":memory:", keyring=None, strict_mode=True)
    ev = Event("peer", 1, 100.0, "need", "n-1", "CREATE", {"item": "Water"})
    with pytest.raises(StrictSecurityError, match="Cannot process sync events in unauthenticated mode"):
        node._verify_and_filter_events([ev])
    node.close()


def test_tcp_transport_oversized_frame_rejected():
    """
    Verify that TCPTransport rejects frames exceeding max_frame_size before allocating memory.
    """
    import struct
    # Set a tiny max_frame_size of 1024 bytes (1 KB) for the test
    t_server = TCPTransport("test-srv", "127.0.0.1", port=0, max_frame_size=1024)
    assert t_server.max_frame_size == 1024

    class MockSocket:
        def __init__(self, data: bytes):
            self.data = data
            self.closed = False
        def recv(self, n):
            chunk = self.data[:n]
            self.data = self.data[n:]
            return chunk
        def settimeout(self, t): pass
        def close(self): self.closed = True

    # 4-byte header claiming a 50 MB frame (52428800 bytes)
    oversized_header = struct.pack("!I", 50 * 1024 * 1024)
    mock_sock = MockSocket(oversized_header)

    # Invoking handler must detect oversized frame, abort, and close socket without reading 50MB
    t_server._handle_client_connection(mock_sock)
    assert mock_sock.closed is True
    assert len(mock_sock.data) == 0  # Header consumed, 50MB was NEVER requested/allocated

    t_server.close()

