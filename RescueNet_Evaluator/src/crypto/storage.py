"""
Persistent Key Storage (KeyStore) for RescueNet Node Identity.

Manages persistent on-disk storage of Ed25519 private identity keys:
- At-rest protection using Argon2id (64 MiB memory, 3 iterations, 4 lanes) + AES-256-GCM.
- Versioned KDF envelope supporting transparent migration.
- BIP-39 compatible deterministic emergency recovery from a 24-word master recovery phrase.
- Fail-closed error handling: Corrupted keys or wrong passphrases raise KeyStoreError.
"""

from __future__ import annotations
import json
import os
import hashlib
from typing import Tuple, Optional, Dict, Any
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.argon2 import Argon2id
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from .peer_manifest import compute_key_fingerprint, validate_ed25519_public_key


class KeyStoreError(Exception):
    """Base exception for KeyStore errors."""
    pass


class KeyDecryptionError(KeyStoreError):
    """Raised when passphrase fails to decrypt the private key."""
    pass


class KeyCorruptedError(KeyStoreError):
    """Raised when stored key file is corrupted or unreadable."""
    pass


# Default Argon2id parameters (OWASP memory-hard recommendation)
ARGON2_PARAMS = {
    "memory_cost": 65536,  # 64 MiB
    "iterations": 3,
    "lanes": 4,
}


def derive_key_argon2(passphrase: str, salt: bytes) -> bytes:
    """Derive 256-bit encryption key using Argon2id."""
    kdf = Argon2id(
        salt=salt,
        length=32,
        iterations=ARGON2_PARAMS["iterations"],
        lanes=ARGON2_PARAMS["lanes"],
        memory_cost=ARGON2_PARAMS["memory_cost"],
    )
    return kdf.derive(passphrase.encode("utf-8"))


def derive_key_pbkdf2_legacy(passphrase: str, salt: bytes, iterations: int = 100_000) -> bytes:
    """Legacy PBKDF2 key derivation for backward compatibility."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=iterations,
    )
    return kdf.derive(passphrase.encode("utf-8"))


class KeyStore:
    """
    Manages persistent on-disk Ed25519 identity keys for a specific node.
    """

    def __init__(self, security_dir: str, node_id: str) -> None:
        self.security_dir = security_dir
        self.node_id = node_id
        self.key_dir = os.path.join(security_dir, node_id)
        self.key_enc_file = os.path.join(self.key_dir, "identity.key.enc")
        self.pub_file = os.path.join(self.key_dir, "identity.pub")
        os.makedirs(self.key_dir, exist_ok=True)

    def has_identity(self) -> bool:
        """Check if persistent identity keys already exist on disk."""
        return os.path.exists(self.key_enc_file) and os.path.exists(self.pub_file)

    def save_identity(
        self,
        private_key: ed25519.Ed25519PrivateKey,
        passphrase: Optional[str] = None,
    ) -> str:
        """
        Encrypt and save the private key and public key to disk.
        Returns the 64-character public key hex string.
        """
        raw_priv_bytes = private_key.private_bytes_raw()
        pub_bytes = private_key.public_key().public_bytes_raw()
        pub_hex = pub_bytes.hex()
        fingerprint = compute_key_fingerprint(pub_hex)

        if passphrase:
            salt = os.urandom(16)
            kdf_key = derive_key_argon2(passphrase, salt)
            nonce = os.urandom(12)
            aesgcm = AESGCM(kdf_key)
            ciphertext = aesgcm.encrypt(nonce, raw_priv_bytes, associated_data=None)

            envelope = {
                "kdf_version": "argon2id_v1",
                "kdf_params": {
                    "memory_cost": ARGON2_PARAMS["memory_cost"],
                    "iterations": ARGON2_PARAMS["iterations"],
                    "lanes": ARGON2_PARAMS["lanes"],
                    "salt": salt.hex(),
                },
                "nonce": nonce.hex(),
                "ciphertext": ciphertext.hex(),
            }
        else:
            # Unencrypted store (used for automated tests or environments with full disk encryption)
            envelope = {
                "kdf_version": "plaintext",
                "raw_key": raw_priv_bytes.hex(),
            }

        # Atomically write key file
        tmp_key = f"{self.key_enc_file}.tmp"
        with open(tmp_key, "w", encoding="utf-8") as f:
            json.dump(envelope, f, indent=2)
        if os.path.exists(self.key_enc_file):
            os.replace(tmp_key, self.key_enc_file)
        else:
            os.rename(tmp_key, self.key_enc_file)

        # Write public key file
        pub_data = {
            "node_id": self.node_id,
            "public_key": pub_hex,
            "fingerprint": fingerprint,
        }
        tmp_pub = f"{self.pub_file}.tmp"
        with open(tmp_pub, "w", encoding="utf-8") as f:
            json.dump(pub_data, f, indent=2)
        if os.path.exists(self.pub_file):
            os.replace(tmp_pub, self.pub_file)
        else:
            os.rename(tmp_pub, self.pub_file)

        return pub_hex

    def load_identity(
        self,
        passphrase: Optional[str] = None,
    ) -> Tuple[ed25519.Ed25519PrivateKey, str]:
        """
        Load and decrypt private key from disk, validating against the stored public key.
        Fails closed: Raises KeyDecryptionError on wrong passphrase, KeyCorruptedError on corruption.
        Returns: (private_key, public_key_hex)
        """
        if not self.has_identity():
            raise KeyStoreError(f"No identity key found at '{self.key_dir}'")

        try:
            with open(self.key_enc_file, "r", encoding="utf-8") as f:
                envelope = json.load(f)
        except Exception as e:
            raise KeyCorruptedError(f"Corrupted key file at '{self.key_enc_file}': {e}") from e

        try:
            with open(self.pub_file, "r", encoding="utf-8") as f:
                pub_data = json.load(f)
                expected_pub_hex = pub_data["public_key"]
        except Exception as e:
            raise KeyCorruptedError(f"Corrupted public key file at '{self.pub_file}': {e}") from e

        kdf_version = envelope.get("kdf_version", "")
        if kdf_version == "plaintext":
            raw_priv_bytes = bytes.fromhex(envelope["raw_key"])
        elif kdf_version == "argon2id_v1":
            if not passphrase:
                raise KeyDecryptionError("Passphrase required to decrypt private key")
            try:
                salt = bytes.fromhex(envelope["kdf_params"]["salt"])
                kdf_key = derive_key_argon2(passphrase, salt)
                nonce = bytes.fromhex(envelope["nonce"])
                ciphertext = bytes.fromhex(envelope["ciphertext"])
                aesgcm = AESGCM(kdf_key)
                raw_priv_bytes = aesgcm.decrypt(nonce, ciphertext, associated_data=None)
            except Exception as e:
                raise KeyDecryptionError(f"Invalid passphrase or corrupted ciphertext: {e}") from e
        elif kdf_version in ("pbkdf2_v1", ""):
            # Legacy PBKDF2 envelope
            if not passphrase:
                raise KeyDecryptionError("Passphrase required to decrypt legacy private key")
            try:
                salt = bytes.fromhex(envelope.get("salt") or envelope.get("kdf_params", {}).get("salt", ""))
                iters = envelope.get("iterations", 100_000)
                kdf_key = derive_key_pbkdf2_legacy(passphrase, salt, iters)
                nonce = bytes.fromhex(envelope["nonce"])
                ciphertext = bytes.fromhex(envelope["ciphertext"])
                aesgcm = AESGCM(kdf_key)
                raw_priv_bytes = aesgcm.decrypt(nonce, ciphertext, associated_data=None)
            except Exception as e:
                raise KeyDecryptionError(f"Invalid passphrase for legacy key: {e}") from e
        else:
            raise KeyCorruptedError(f"Unsupported KDF version: '{kdf_version}'")

        try:
            priv_key = ed25519.Ed25519PrivateKey.from_private_bytes(raw_priv_bytes)
            computed_pub_hex = priv_key.public_key().public_bytes_raw().hex()
            if computed_pub_hex.lower() != expected_pub_hex.lower():
                raise KeyCorruptedError(
                    f"Derived public key ({computed_pub_hex}) does not match stored public key ({expected_pub_hex})"
                )
            return priv_key, computed_pub_hex
        except Exception as e:
            if isinstance(e, KeyStoreError):
                raise
            raise KeyCorruptedError(f"Failed to instantiate Ed25519 key from decrypted bytes: {e}") from e

    def load_or_create_identity(
        self,
        passphrase: Optional[str] = None,
    ) -> Tuple[ed25519.Ed25519PrivateKey, str]:
        """
        Load existing identity from disk, or generate a fresh keypair and persist it.
        """
        if self.has_identity():
            return self.load_identity(passphrase)
        priv = ed25519.Ed25519PrivateKey.generate()
        pub_hex = self.save_identity(priv, passphrase)
        return priv, pub_hex

    @staticmethod
    def derive_seed_from_recovery_phrase(recovery_phrase: str, passphrase: str = "") -> bytes:
        """
        Derive a deterministic 32-byte Ed25519 seed from a 24-word recovery phrase or master seed string.
        Uses standard PBKDF2-HMAC-SHA512 (BIP-39 derivation standard).
        """
        words = recovery_phrase.strip().split()
        if len(words) not in (12, 18, 24) and len(recovery_phrase.strip()) < 16:
            raise ValueError("Recovery phrase must contain 12, 18, or 24 words or be >= 16 characters")

        clean_mnemonic = " ".join(words).encode("utf-8")
        salt = ("mnemonic" + passphrase).encode("utf-8")
        # BIP-39 standard 2048 rounds of PBKDF2-HMAC-SHA512
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA512(),
            length=64,
            salt=salt,
            iterations=2048,
        )
        seed_64 = kdf.derive(clean_mnemonic)
        # Use first 32 bytes as Ed25519 seed
        return seed_64[:32]

    def recover_identity(
        self,
        recovery_phrase: str,
        new_passphrase: Optional[str] = None,
    ) -> Tuple[ed25519.Ed25519PrivateKey, str]:
        """
        Recover node identity from emergency recovery phrase, reset PIN/passphrase, and re-save.
        """
        seed_32 = self.derive_seed_from_recovery_phrase(recovery_phrase)
        priv = ed25519.Ed25519PrivateKey.from_private_bytes(seed_32)
        pub_hex = self.save_identity(priv, new_passphrase)
        return priv, pub_hex
