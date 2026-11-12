"""
Asymmetric Digital Signatures (Ed25519) for Anti-Tampering and Authentication.

Design Decisions:
1. Why Ed25519?
   - Modern, high-speed public-key signature system.
   - Fixed 64-byte signatures and 32-byte public keys (minimal wire bandwidth overhead).
   - Immune to side-channel timing attacks.
2. Anti-Forgery Guarantee:
   - Every event is signed over its canonical bytes (excluding the signature field itself).
   - If an adversary attempts to tamper with the sequence counter, timestamp, or payload,
     the cryptographic signature verification fails immediately.
   - Forged updates are rejected at the door before ever touching SQLite.
"""

from __future__ import annotations
from typing import Tuple
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.exceptions import InvalidSignature
from events.event import Event


class SignatureError(Exception):
    """Raised when signature verification fails."""
    pass


class Signer:
    """
    Handles Ed25519 key generation, signing, and signature verification.
    """

    @staticmethod
    def generate_keypair() -> Tuple[ed25519.Ed25519PrivateKey, str]:
        """
        Generate a new Ed25519 keypair.
        Returns: (private_key_object, public_key_hex_string)
        """
        priv = ed25519.Ed25519PrivateKey.generate()
        pub_bytes = priv.public_key().public_bytes_raw()
        return priv, pub_bytes.hex()

    @staticmethod
    def sign_event(event: Event, private_key: ed25519.Ed25519PrivateKey) -> Event:
        """
        Cryptographically sign the canonical content bytes of an event.
        Returns a new Event instance with the signature field populated.
        """
        canonical_bytes = event.canonical_content_bytes()
        sig_bytes = private_key.sign(canonical_bytes)
        sig_hex = sig_bytes.hex()

        # Reconstruct event with signature populated
        return Event(
            node_id=event.node_id,
            counter=event.counter,
            timestamp=event.timestamp,
            entity_type=event.entity_type,
            entity_id=event.entity_id,
            operation=event.operation,
            payload=event.payload,
            signature=sig_hex,
            event_id=event.event_id,
        )

    @staticmethod
    def verify_event(event: Event, public_key_hex: str) -> bool:
        """
        Verify that the event's signature is valid for the given public key.
        Returns True if signature is valid, False if tampered or missing.
        """
        if not event.signature:
            return False

        try:
            pub_bytes = bytes.fromhex(public_key_hex)
            public_key = ed25519.Ed25519PublicKey.from_public_bytes(pub_bytes)

            sig_bytes = bytes.fromhex(event.signature)
            canonical_bytes = event.canonical_content_bytes()

            public_key.verify(sig_bytes, canonical_bytes)
            return True
        except (InvalidSignature, ValueError):
            return False
