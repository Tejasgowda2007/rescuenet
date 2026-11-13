"""
Field-Level Encryption at Rest for Sensitive Disaster Data.

Design Decisions:
1. Field-Level vs Full-Database Encryption:
   - Metadata (entity_type, entity_id, counter, timestamp) must remain unencrypted
     so offline nodes can build version vectors and execute anti-entropy sync.
   - Personally Identifiable Information (PII) such as victim names, medical conditions,
     shelter addresses, and child identities are encrypted with AES-256-GCM.
2. Authenticated Encryption:
   - AES-GCM provides both confidentiality and tamper-evidence (an adversary cannot
     modify ciphertext without failing the GCM authentication tag).
3. Key Derivation:
   - 256-bit symmetric keys are derived from volunteer passphrases using PBKDF2-HMAC-SHA256
     with a random 16-byte salt and 100,000 iterations.
"""

from __future__ import annotations
import os
import json
import hashlib
from typing import Dict, Any, Set, Optional, List
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes


# Default fields containing sensitive human data in disaster response
DEFAULT_SENSITIVE_FIELDS: Set[str] = {
    "name",
    "medical_notes",
    "condition",
    "phone",
    "contact",
    "last_seen",
    "current_location",
    "address",
    "details",
    "beneficiary",
    "notes",
}


class CryptoError(Exception):
    """Raised on encryption or decryption failure (e.g. wrong passphrase or tampering)."""
    pass


class FieldEncryptor:
    """
    Encrypts and decrypts sensitive payload fields using passphrase-derived AES-256-GCM keys.
    """

    _key_cache: Dict[tuple, bytes] = {}

    @classmethod
    def derive_key(cls, passphrase: str, salt: bytes) -> bytes:
        """
        Derive a 256-bit AES key from a passphrase and salt using PBKDF2-HMAC-SHA256.
        Caches key in memory to prevent repeated 100k iteration overhead within the process.
        """
        cache_key = (passphrase, salt)
        if cache_key in cls._key_cache:
            return cls._key_cache[cache_key]

        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100_000,
        )
        derived = kdf.derive(passphrase.encode("utf-8"))
        cls._key_cache[cache_key] = derived
        return derived

    @classmethod
    def encrypt_value(cls, value: Any, passphrase: str, salt: bytes) -> Dict[str, Any]:
        """
        Encrypt a single arbitrary Python value (string, dict, number).
        Returns a structured envelope: {'__enc__': True, 'nonce': hex, 'data': hex}.
        """
        key = cls.derive_key(passphrase, salt)
        aesgcm = AESGCM(key)
        nonce = os.urandom(12)  # 96-bit unique standard GCM nonce

        plaintext_bytes = json.dumps(value, sort_keys=True).encode("utf-8")
        ciphertext = aesgcm.encrypt(nonce, plaintext_bytes, associated_data=None)

        return {
            "__enc__": True,
            "nonce": nonce.hex(),
            "data": ciphertext.hex(),
        }

    @classmethod
    def decrypt_value(cls, envelope: Dict[str, Any], passphrase: str, salt: bytes) -> Any:
        """
        Decrypt an encrypted envelope using the passphrase and salt.
        Raises CryptoError if passphrase is wrong or ciphertext was modified.
        """
        if not isinstance(envelope, dict) or not envelope.get("__enc__"):
            return envelope  # Not encrypted

        try:
            key = cls.derive_key(passphrase, salt)
            aesgcm = AESGCM(key)
            nonce = bytes.fromhex(envelope["nonce"])
            ciphertext = bytes.fromhex(envelope["data"])

            plaintext_bytes = aesgcm.decrypt(nonce, ciphertext, associated_data=None)
            return json.loads(plaintext_bytes.decode("utf-8"))
        except Exception as e:
            raise CryptoError(f"Decryption failed (invalid passphrase or corrupted data): {e}") from e

    @classmethod
    def encrypt_payload(
        cls,
        payload: Dict[str, Any],
        passphrase: str,
        salt: bytes,
        sensitive_fields: Optional[Set[str]] = None,
    ) -> Dict[str, Any]:
        """
        Traverse payload and encrypt all sensitive fields in-place into safe storage format.
        """
        targets = sensitive_fields if sensitive_fields is not None else DEFAULT_SENSITIVE_FIELDS
        encrypted_payload = dict(payload)

        for key, val in payload.items():
            if key in targets and val is not None:
                encrypted_payload[key] = cls.encrypt_value(val, passphrase, salt)

        return encrypted_payload

    @classmethod
    def decrypt_payload(
        cls,
        payload: Dict[str, Any],
        passphrase: str,
        salt: bytes,
    ) -> Dict[str, Any]:
        """
        Decrypt all encrypted fields inside a payload, returning cleartext for authorized display.
        """
        decrypted_payload = dict(payload)

        for key, val in payload.items():
            if isinstance(val, dict) and val.get("__enc__"):
                decrypted_payload[key] = cls.decrypt_value(val, passphrase, salt)

        return decrypted_payload

    @classmethod
    def derive_mesh_key(cls, passphrase: str, salt: bytes) -> bytes:
        """
        Derive a 256-bit Mesh Pre-Shared Key (Mesh PSK) from passphrase and salt.
        Used to eliminate ad-hoc shared salt usage.
        """
        return cls.derive_key(passphrase, salt)


class MeshCipher:
    """
    Field-level authenticated symmetric encryption using a 256-bit Mesh Pre-Shared Key (Mesh PSK).
    Supports Key IDs (kid) for key versioning and dual-key historical event decryption.
    """

    def __init__(
        self,
        mesh_key: bytes,
        legacy_passphrase: Optional[str] = None,
        legacy_salt: Optional[bytes] = None,
    ) -> None:
        if len(mesh_key) != 32:
            raise ValueError(f"Mesh key must be exactly 32 bytes (256 bits), got {len(mesh_key)}")
        self.mesh_key = mesh_key
        self.kid = hashlib.sha256(mesh_key).hexdigest()[:8]
        self.historical_keys: Dict[str, bytes] = {}
        self.legacy_passphrase = legacy_passphrase
        self.legacy_salt = legacy_salt

    def rotate_key(self, new_key: bytes) -> str:
        """
        Rotate to a new 256-bit key. Pushes active key to historical keys.
        Returns the new Key ID (kid).
        """
        if len(new_key) != 32:
            raise ValueError(f"New mesh key must be exactly 32 bytes (256 bits), got {len(new_key)}")
        # Save old key to historical keys
        self.historical_keys[self.kid] = self.mesh_key
        self.mesh_key = new_key
        self.kid = hashlib.sha256(new_key).hexdigest()[:8]
        return self.kid

    def add_historical_key(self, key_bytes: bytes) -> str:
        """Add a prior key to historical keys for decrypting older audit logs."""
        if len(key_bytes) != 32:
            raise ValueError("Historical key must be exactly 32 bytes")
        kid = hashlib.sha256(key_bytes).hexdigest()[:8]
        self.historical_keys[kid] = key_bytes
        return kid

    def encrypt_value(self, value: Any, kid: Optional[str] = None) -> Dict[str, Any]:
        """
        Encrypt a single value using AES-256-GCM with a fresh 96-bit CSPRNG nonce.
        Tagged with active Key ID for versioning.
        """
        target_key = self.mesh_key
        target_kid = self.kid
        if kid and kid in self.historical_keys:
            target_key = self.historical_keys[kid]
            target_kid = kid

        aesgcm = AESGCM(target_key)
        nonce = os.urandom(12)  # 96-bit unique nonce
        plaintext_bytes = json.dumps(value, sort_keys=True).encode("utf-8")
        ciphertext = aesgcm.encrypt(nonce, plaintext_bytes, associated_data=None)

        return {
            "__enc__": True,
            "kid": target_kid,
            "nonce": nonce.hex(),
            "data": ciphertext.hex(),
        }

    def decrypt_value(self, envelope: Dict[str, Any]) -> Any:
        """
        Decrypt an encrypted envelope.
        Checks kid for matching active/historical key, with fallback to legacy derivation.
        """
        if not isinstance(envelope, dict) or not envelope.get("__enc__"):
            return envelope

        env_kid = envelope.get("kid")
        nonce_hex = envelope.get("nonce")
        data_hex = envelope.get("data")
        if not nonce_hex or not data_hex:
            raise CryptoError("Malformed encryption envelope: missing nonce or data")

        try:
            nonce = bytes.fromhex(nonce_hex)
            ciphertext = bytes.fromhex(data_hex)
        except ValueError as e:
            raise CryptoError(f"Invalid hex encoding in envelope: {e}") from e

        # 1. If kid matches active key
        if env_kid == self.kid or env_kid is None:
            try:
                aesgcm = AESGCM(self.mesh_key)
                plaintext = aesgcm.decrypt(nonce, ciphertext, associated_data=None)
                return json.loads(plaintext.decode("utf-8"))
            except Exception:
                if env_kid is not None:
                    # Explicit kid failed on active key
                    pass

        # 2. Check historical keys
        if env_kid and env_kid in self.historical_keys:
            try:
                aesgcm = AESGCM(self.historical_keys[env_kid])
                plaintext = aesgcm.decrypt(nonce, ciphertext, associated_data=None)
                return json.loads(plaintext.decode("utf-8"))
            except Exception as e:
                raise CryptoError(f"Decryption failed for historical key '{env_kid}': {e}") from e

        # If envelope has unknown kid but we have other historical keys, try them
        for h_kid, h_key in self.historical_keys.items():
            if h_kid != env_kid:
                try:
                    aesgcm = AESGCM(h_key)
                    plaintext = aesgcm.decrypt(nonce, ciphertext, associated_data=None)
                    return json.loads(plaintext.decode("utf-8"))
                except Exception:
                    continue

        # 3. Fallback: Legacy PBKDF2 decryption if legacy credentials available
        if self.legacy_passphrase and self.legacy_salt:
            try:
                return FieldEncryptor.decrypt_value(envelope, self.legacy_passphrase, self.legacy_salt)
            except Exception:
                pass

        raise CryptoError(
            f"Decryption failed: Key mismatch or tampered ciphertext (kid: '{env_kid}')"
        )

    def encrypt_payload(
        self,
        payload: Dict[str, Any],
        sensitive_fields: Optional[Set[str]] = None,
    ) -> Dict[str, Any]:
        """Traverse payload and encrypt sensitive fields using active Mesh PSK."""
        targets = sensitive_fields if sensitive_fields is not None else DEFAULT_SENSITIVE_FIELDS
        encrypted_payload = dict(payload)

        for key, val in payload.items():
            if key in targets and val is not None:
                encrypted_payload[key] = self.encrypt_value(val)

        return encrypted_payload

    def decrypt_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Decrypt all encrypted fields inside a payload using active/historical keys."""
        decrypted_payload = dict(payload)

        for key, val in payload.items():
            if isinstance(val, dict) and val.get("__enc__"):
                decrypted_payload[key] = self.decrypt_value(val)

        return decrypted_payload
