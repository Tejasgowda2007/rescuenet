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
from typing import Dict, Any, Set, Optional
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
