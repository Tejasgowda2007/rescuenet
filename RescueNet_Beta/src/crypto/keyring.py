"""
Node Keyring: Manages cryptographic credentials, passphrases, and peer trust.
Supports persistent KeyStore and PeerManifest for zero-trust offline operation.
"""

from __future__ import annotations
import os
from typing import Dict, Optional, Tuple, Set, Any
from cryptography.hazmat.primitives.asymmetric import ed25519
from events.event import Event
from .signatures import Signer
from .ciphers import FieldEncryptor, MeshCipher
from .storage import KeyStore
from .peer_manifest import PeerManifest, validate_ed25519_public_key


class NodeKeyring:
    """
    Manages local keys, encryption passphrase, Mesh PSK, and the trusted public keys of peer nodes.
    Supports both in-memory operation (for tests/simulations) and persistent on-disk operation.
    """

    def __init__(
        self,
        node_id: str,
        passphrase: Optional[str] = None,
        salt: Optional[bytes] = None,
        private_key: Optional[ed25519.Ed25519PrivateKey] = None,
        public_key_hex: Optional[str] = None,
        keys_dir: Optional[str] = None,
        mesh_key: Optional[bytes] = None,
    ) -> None:
        self.node_id = node_id
        self.passphrase = passphrase
        self.salt = salt if salt is not None else os.urandom(16)
        self.keys_dir = keys_dir
        self.keystore: Optional[KeyStore] = None
        self.manifest: Optional[PeerManifest] = None

        # 1. Identity Keypair resolution (Persistent KeyStore vs explicit vs ephemeral)
        if keys_dir is not None:
            self.keystore = KeyStore(keys_dir, node_id)
            self.manifest = PeerManifest(os.path.join(keys_dir, node_id))
            if private_key is not None and public_key_hex is not None:
                self.private_key = private_key
                self.public_key_hex = public_key_hex
                self.keystore.save_identity(private_key, passphrase)
            else:
                self.private_key, self.public_key_hex = self.keystore.load_or_create_identity(passphrase)
            # Ensure self is enrolled in manifest
            if not self.manifest.is_trusted(self.node_id):
                self.manifest.enroll_peer(self.node_id, self.public_key_hex, alias="self", role="self")
            self.trusted_peers: Dict[str, str] = self.manifest.get_trusted_keys_dict()
            self.revoked_peers: Set[str] = self.manifest.get_revoked_set()
        else:
            if private_key is not None and public_key_hex is not None:
                self.private_key = private_key
                self.public_key_hex = public_key_hex
            else:
                self.private_key, self.public_key_hex = Signer.generate_keypair()

            # In-memory maps
            self.trusted_peers = {self.node_id: self.public_key_hex}
            self.revoked_peers = set()

        # 2. Symmetric Cipher resolution (MeshCipher with 256-bit PSK vs FieldEncryptor)
        self.mesh_cipher: Optional[MeshCipher] = None
        if mesh_key is not None:
            self.mesh_cipher = MeshCipher(
                mesh_key,
                legacy_passphrase=self.passphrase,
                legacy_salt=self.salt,
            )
        elif self.passphrase is not None:
            # Derive 256-bit Mesh PSK from passphrase & salt
            derived_key = FieldEncryptor.derive_mesh_key(self.passphrase, self.salt)
            self.mesh_cipher = MeshCipher(
                derived_key,
                legacy_passphrase=self.passphrase,
                legacy_salt=self.salt,
            )

    def register_peer(self, peer_id: str, peer_public_key_hex: str, alias: str = "", role: str = "responder") -> None:
        """Register a peer's trusted Ed25519 public key."""
        if self.is_revoked(peer_id):
            return
        validate_ed25519_public_key(peer_public_key_hex)
        if self.manifest:
            self.manifest.enroll_peer(peer_id, peer_public_key_hex, alias=alias, role=role)
            self.trusted_peers = self.manifest.get_trusted_keys_dict()
        else:
            self.trusted_peers[peer_id] = peer_public_key_hex

    def revoke_peer(
        self,
        peer_id: str,
        reason: str = "COMPROMISED",
        effective_counter: Optional[int] = None,
    ) -> None:
        """
        Pillar 4 Kill-Switch: Revoke and blacklist a device (e.g. seized by hostile actor).
        Freezes its ability to inject data into the mesh network.
        """
        self.revoked_peers.add(peer_id)
        if peer_id in self.trusted_peers:
            del self.trusted_peers[peer_id]

        if self.manifest:
            self.manifest.revoke_peer(peer_id, reason=reason, effective_counter=effective_counter)
            self.trusted_peers = self.manifest.get_trusted_keys_dict()
            self.revoked_peers = self.manifest.get_revoked_set()

    def restore_revoked_peer(
        self,
        peer_id: str,
        peer_public_key_hex: str,
        expected_fingerprint: str,
        reason: str = "OFFICIAL_RECOVERY",
        authorized_by: str = "coordinator",
    ) -> None:
        """Explicit recovery operation to restore a revoked peer with verified fingerprint."""
        if self.manifest:
            self.manifest.restore_revoked_peer(
                node_id=peer_id,
                public_key_hex=peer_public_key_hex,
                expected_fingerprint=expected_fingerprint,
                reason=reason,
                authorized_by=authorized_by,
            )
            self.trusted_peers = self.manifest.get_trusted_keys_dict()
            self.revoked_peers = self.manifest.get_revoked_set()
        else:
            validate_ed25519_public_key(peer_public_key_hex)
            if peer_id in self.revoked_peers:
                self.revoked_peers.remove(peer_id)
            self.trusted_peers[peer_id] = peer_public_key_hex

    def is_revoked(self, peer_id: str) -> bool:
        """Check if a device has been blacklisted across the cryptographic ring."""
        if self.manifest:
            return self.manifest.is_revoked(peer_id)
        return peer_id in self.revoked_peers

    def sign_event(self, event: Event) -> Event:
        """Sign an event generated by this node."""
        if self.private_key is None:
            return event
        return Signer.sign_event(event, self.private_key)

    def verify_event(self, event: Event) -> bool:
        """
        Verify that an incoming event was signed by its purported author.
        If the author has been revoked or is not in trusted_peers, returns False.
        """
        if self.is_revoked(event.node_id):
            return False
        pub_key = self.trusted_peers.get(event.node_id)
        if not pub_key:
            return False
        return Signer.verify_event(event, pub_key)

    def encrypt_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Encrypt sensitive fields using MeshCipher (or legacy FieldEncryptor)."""
        if self.mesh_cipher is not None:
            return self.mesh_cipher.encrypt_payload(payload)
        if not self.passphrase:
            return payload
        return FieldEncryptor.encrypt_payload(payload, self.passphrase, self.salt)

    def decrypt_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Decrypt sensitive fields for local display and triage."""
        if self.mesh_cipher is not None:
            return self.mesh_cipher.decrypt_payload(payload)
        if not self.passphrase:
            return payload
        return FieldEncryptor.decrypt_payload(payload, self.passphrase, self.salt)

    def rotate_mesh_key(self, new_mesh_key: bytes) -> str:
        """Rotate the active 256-bit Mesh PSK. Returns the new Key ID."""
        if self.mesh_cipher is None:
            self.mesh_cipher = MeshCipher(new_mesh_key, self.passphrase, self.salt)
            return self.mesh_cipher.kid
        return self.mesh_cipher.rotate_key(new_mesh_key)
