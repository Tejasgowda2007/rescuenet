"""
Peer Trust Manifest and Revocation Management for RescueNet.

Manages persistent JSON trust stores for offline peer enrollment and revocation:
- trusted_peers.json: Registered peer public keys, roles, and fingerprints.
- revoked_peers.json: Blacklisted/compromised device IDs and effective counters.

Fail-Closed Architecture:
1. Corrupted or unreadable manifests raise PeerManifestCorruptedError immediately.
2. Normal enrollment never clears a revocation.
3. Restoring a revoked peer requires explicit fingerprint verification.
"""

from __future__ import annotations
import json
import os
import time
import hashlib
from typing import Dict, List, Optional, Any, Set
from cryptography.hazmat.primitives.asymmetric import ed25519


class PeerManifestError(Exception):
    """Base exception for peer manifest errors."""
    pass


class PeerManifestCorruptedError(PeerManifestError):
    """Raised when trusted_peers.json or revoked_peers.json cannot be read or parsed."""
    pass


class RevokedPeerEnrollmentError(PeerManifestError):
    """Raised when an attempt is made to enroll a revoked peer without explicit recovery."""
    pass


class InvalidPublicKeyError(PeerManifestError):
    """Raised when an Ed25519 public key is invalid, corrupted, or not 32 bytes."""
    pass


class FingerprintMismatchError(PeerManifestError):
    """Raised when explicit restoration fingerprint does not match the public key."""
    pass


def validate_ed25519_public_key(public_key_hex: str) -> bytes:
    """
    Validate that the public key is a valid 32-byte (64-character hex) Ed25519 key.
    Returns the raw 32 bytes if valid, raises InvalidPublicKeyError otherwise.
    """
    if not isinstance(public_key_hex, str):
        raise InvalidPublicKeyError("Public key must be a string")
    
    clean_hex = public_key_hex.strip()
    if len(clean_hex) != 64:
        raise InvalidPublicKeyError(
            f"Ed25519 public key hex must be exactly 64 characters (32 bytes), got {len(clean_hex)}"
        )
    
    try:
        raw_bytes = bytes.fromhex(clean_hex)
    except ValueError as e:
        raise InvalidPublicKeyError(f"Invalid hexadecimal encoding in public key: {e}") from e
    
    if len(raw_bytes) != 32:
        raise InvalidPublicKeyError(
            f"Ed25519 public key must be exactly 32 bytes, got {len(raw_bytes)}"
        )
    
    try:
        # Cryptographic validation
        ed25519.Ed25519PublicKey.from_public_bytes(raw_bytes)
    except Exception as e:
        raise InvalidPublicKeyError(f"Cryptographically invalid Ed25519 public key: {e}") from e
    
    return raw_bytes


def compute_key_fingerprint(public_key_hex: str) -> str:
    """
    Calculate full 32-byte SHA-256 fingerprint: SHA256:XX:XX:...:XX (32 colon-separated byte pairs).
    """
    raw_bytes = validate_ed25519_public_key(public_key_hex)
    digest = hashlib.sha256(raw_bytes).hexdigest().upper()
    # Full 32 bytes (64 hex characters) -> 32 pairs
    chunks = [digest[i:i + 2] for i in range(0, 64, 2)]
    return "SHA256:" + ":".join(chunks)


class PeerManifest:
    """
    Manages trusted and revoked peers with atomic disk persistence and fail-closed integrity.
    """

    def __init__(self, manifest_dir: Optional[str] = None) -> None:
        self.manifest_dir = manifest_dir
        self.trusted_peers_file = (
            os.path.join(manifest_dir, "trusted_peers.json") if manifest_dir else None
        )
        self.revoked_peers_file = (
            os.path.join(manifest_dir, "revoked_peers.json") if manifest_dir else None
        )

        # In-memory maps:
        # trusted_peers: {node_id: {"public_key": hex, "alias": str, "role": str, "enrolled_at": float, "fingerprint": str}}
        self.trusted_peers: Dict[str, Dict[str, Any]] = {}
        # revoked_peers: {node_id: {"reason": str, "revoked_at": float, "effective_counter": Optional[int]}}
        self.revoked_peers: Dict[str, Dict[str, Any]] = {}

        if self.manifest_dir:
            os.makedirs(self.manifest_dir, exist_ok=True)
            self._load()

    def _load(self) -> None:
        """
        Load manifest files from disk.
        Fails closed: If any file exists but is corrupted or invalid JSON, raises PeerManifestCorruptedError.
        """
        if self.trusted_peers_file and os.path.exists(self.trusted_peers_file):
            try:
                with open(self.trusted_peers_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if not isinstance(data, dict):
                        raise ValueError("trusted_peers.json must contain a JSON object")
                    # Validate all existing public keys in the file
                    for nid, record in data.items():
                        if not isinstance(record, dict) or "public_key" not in record:
                            raise ValueError(f"Record for '{nid}' missing 'public_key'")
                        validate_ed25519_public_key(record["public_key"])
                    self.trusted_peers = data
            except Exception as e:
                raise PeerManifestCorruptedError(
                    f"Fail-closed: Corrupted or unreadable trusted_peers.json at '{self.trusted_peers_file}': {e}"
                ) from e

        if self.revoked_peers_file and os.path.exists(self.revoked_peers_file):
            try:
                with open(self.revoked_peers_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if not isinstance(data, dict):
                        raise ValueError("revoked_peers.json must contain a JSON object")
                    self.revoked_peers = data
            except Exception as e:
                raise PeerManifestCorruptedError(
                    f"Fail-closed: Corrupted or unreadable revoked_peers.json at '{self.revoked_peers_file}': {e}"
                ) from e

    def _save(self) -> None:
        """Atomically persist manifest files to disk using temp file write + rename."""
        if self.trusted_peers_file:
            tmp_trusted = f"{self.trusted_peers_file}.tmp"
            with open(tmp_trusted, "w", encoding="utf-8") as f:
                json.dump(self.trusted_peers, f, indent=2, sort_keys=True)
            if os.path.exists(self.trusted_peers_file):
                os.replace(tmp_trusted, self.trusted_peers_file)
            else:
                os.rename(tmp_trusted, self.trusted_peers_file)

        if self.revoked_peers_file:
            tmp_revoked = f"{self.revoked_peers_file}.tmp"
            with open(tmp_revoked, "w", encoding="utf-8") as f:
                json.dump(self.revoked_peers, f, indent=2, sort_keys=True)
            if os.path.exists(self.revoked_peers_file):
                os.replace(tmp_revoked, self.revoked_peers_file)
            else:
                os.rename(tmp_revoked, self.revoked_peers_file)

    def enroll_peer(
        self,
        node_id: str,
        public_key_hex: str,
        alias: str = "",
        role: str = "responder",
        persist: bool = True,
    ) -> Dict[str, Any]:
        """
        Enroll a new peer's trusted Ed25519 public key.
        Security Rule: Normal enrollment NEVER clears a revocation.
        """
        if self.is_revoked(node_id):
            raise RevokedPeerEnrollmentError(
                f"Cannot enroll peer '{node_id}': Peer has been revoked. "
                "Use explicit restore_revoked_peer() with verified fingerprint to restore trust."
            )

        validate_ed25519_public_key(public_key_hex)
        fingerprint = compute_key_fingerprint(public_key_hex)

        record = {
            "public_key": public_key_hex,
            "alias": alias or node_id,
            "role": role,
            "enrolled_at": time.time(),
            "fingerprint": fingerprint,
        }
        self.trusted_peers[node_id] = record

        if persist and self.manifest_dir:
            self._save()

        return record

    def revoke_peer(
        self,
        node_id: str,
        reason: str = "COMPROMISED",
        effective_counter: Optional[int] = None,
        persist: bool = True,
    ) -> None:
        """
        Revoke and blacklist a device. Freezes its ability to inject data into the mesh.
        """
        self.revoked_peers[node_id] = {
            "reason": reason,
            "revoked_at": time.time(),
            "effective_counter": effective_counter,
        }
        # Remove from trusted_peers
        if node_id in self.trusted_peers:
            del self.trusted_peers[node_id]

        if persist and self.manifest_dir:
            self._save()

    def restore_revoked_peer(
        self,
        node_id: str,
        public_key_hex: str,
        expected_fingerprint: str,
        reason: str = "OFFICIAL_RECOVERY",
        authorized_by: str = "coordinator",
        alias: str = "",
        role: str = "responder",
        persist: bool = True,
    ) -> Dict[str, Any]:
        """
        Explicit recovery operation to restore a revoked peer.
        Requires exact match of the complete 32-byte SHA-256 fingerprint.
        """
        validate_ed25519_public_key(public_key_hex)
        actual_fingerprint = compute_key_fingerprint(public_key_hex)

        clean_expected = expected_fingerprint.strip().upper()
        clean_actual = actual_fingerprint.strip().upper()
        if clean_expected != clean_actual:
            raise FingerprintMismatchError(
                f"Fingerprint mismatch during peer restoration for '{node_id}'. "
                f"Expected: {clean_expected}, Actual: {clean_actual}"
            )

        # Clear revocation
        if node_id in self.revoked_peers:
            del self.revoked_peers[node_id]

        # Re-enroll with restoration audit metadata
        record = {
            "public_key": public_key_hex,
            "alias": alias or node_id,
            "role": role,
            "enrolled_at": time.time(),
            "restored_at": time.time(),
            "restoration_reason": reason,
            "authorized_by": authorized_by,
            "fingerprint": actual_fingerprint,
        }
        self.trusted_peers[node_id] = record

        if persist and self.manifest_dir:
            self._save()

        return record

    def is_revoked(self, node_id: str) -> bool:
        """Check if node_id is in the revocation blacklist."""
        return node_id in self.revoked_peers

    def is_trusted(self, node_id: str) -> bool:
        """Check if node_id is currently enrolled and not revoked."""
        return (node_id in self.trusted_peers) and not self.is_revoked(node_id)

    def get_public_key(self, node_id: str) -> Optional[str]:
        """Get the Ed25519 public key hex string for an enrolled node."""
        if self.is_revoked(node_id):
            return None
        record = self.trusted_peers.get(node_id)
        return record["public_key"] if record else None

    def get_trusted_keys_dict(self) -> Dict[str, str]:
        """Return a mapping of {node_id: public_key_hex} for all currently trusted peers."""
        return {
            nid: rec["public_key"]
            for nid, rec in self.trusted_peers.items()
            if not self.is_revoked(nid)
        }

    def get_revoked_set(self) -> Set[str]:
        """Return a set of all revoked node_ids."""
        return set(self.revoked_peers.keys())
