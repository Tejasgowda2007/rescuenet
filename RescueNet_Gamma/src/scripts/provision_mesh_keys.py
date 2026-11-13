"""
Offline Pre-Deployment Provisioning Utility for RescueNet.

Generates offline cryptographic bundles for Alpha, Beta, and Gamma laptops:
- Shared 256-bit Mesh Pre-Shared Key (Mesh PSK) for AES-256-GCM.
- Independent Ed25519 identity keypairs for each station.
- Unified trusted_peers.json manifest pre-enrolling all station public keys.
- Output staged for direct copy to FAT32 emergency deployment USB drives.
"""

from __future__ import annotations
import argparse
import os
import sys
import json
import secrets
from typing import List, Dict, Any

# Ensure project root is on sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from crypto.signatures import Signer
from crypto.peer_manifest import compute_key_fingerprint
from crypto.storage import KeyStore


DEFAULT_NODES = [
    {"id": "alpha-harbor", "alias": "Harbor Command Center", "role": "coordinator"},
    {"id": "beta-hospital", "alias": "Field Hospital Triage", "role": "medical"},
    {"id": "gamma-mountain", "alias": "Mountain Shelter Relay", "role": "relay"},
]


def provision_cluster(
    output_dir: str,
    nodes: List[Dict[str, str]] = DEFAULT_NODES,
    passphrase: str = "",
) -> Dict[str, Any]:
    """Generate complete offline provisioning bundle for the disaster cluster."""
    os.makedirs(output_dir, exist_ok=True)

    # 1. Generate 256-bit Mesh PSK (CSPRNG)
    mesh_psk_bytes = secrets.token_bytes(32)
    mesh_psk_hex = mesh_psk_bytes.hex()

    # 2. Generate Ed25519 identity keys for each node
    generated_keys: Dict[str, Any] = {}
    trusted_manifest: Dict[str, Any] = {}

    for node_info in nodes:
        nid = node_info["id"]
        priv_key, pub_hex = Signer.generate_keypair()
        fp = compute_key_fingerprint(pub_hex)
        generated_keys[nid] = {
            "priv_key": priv_key,
            "pub_hex": pub_hex,
            "info": node_info,
            "fingerprint": fp,
        }
        trusted_manifest[nid] = {
            "public_key": pub_hex,
            "alias": node_info.get("alias", nid),
            "role": node_info.get("role", "responder"),
            "fingerprint": fp,
        }

    # 3. Write staging folders for each node
    for nid, data in generated_keys.items():
        node_stage_dir = os.path.join(output_dir, nid)
        os.makedirs(node_stage_dir, exist_ok=True)

        # Save identity key using KeyStore
        keystore = KeyStore(output_dir, nid)
        keystore.save_identity(data["priv_key"], passphrase=passphrase if passphrase else None)

        # Write unified trusted_peers.json
        manifest_path = os.path.join(node_stage_dir, "trusted_peers.json")
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(trusted_manifest, f, indent=2, sort_keys=True)

        # Write empty revoked_peers.json
        revoked_path = os.path.join(node_stage_dir, "revoked_peers.json")
        with open(revoked_path, "w", encoding="utf-8") as f:
            json.dump({}, f, indent=2)

        # Write mesh_config.json
        config_path = os.path.join(node_stage_dir, "mesh_config.json")
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump({
                "cluster_name": "RESCUENET-OFFLINE-CLUSTER",
                "mesh_psk_hex": mesh_psk_hex,
                "node_id": nid,
                "role": data["info"].get("role", "responder"),
            }, f, indent=2)

    # Master deployment summary for Base Camp
    summary = {
        "mesh_psk_hex": mesh_psk_hex,
        "nodes": [
            {
                "id": nid,
                "public_key": data["pub_hex"],
                "fingerprint": data["fingerprint"],
                "role": data["info"].get("role", "responder"),
            }
            for nid, data in generated_keys.items()
        ],
    }
    with open(os.path.join(output_dir, "DEPLOYMENT_SUMMARY.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    return summary


def main():
    parser = argparse.ArgumentParser(description="RescueNet Offline Provisioning Tool")
    parser.add_argument("--output-dir", default="./mesh_provision_bundle", help="Target output folder")
    parser.add_argument("--passphrase", default="", help="Optional PIN/passphrase to encrypt private keys")
    args = parser.parse_args()

    print(f"Provisioning RescueNet offline keys to '{args.output_dir}'...")
    summary = provision_cluster(args.output_dir, passphrase=args.passphrase)
    print(f"[OK] Mesh PSK Generated: {summary['mesh_psk_hex'][:16]}... (256-bit)")
    for n in summary["nodes"]:
        print(f"  * {n['id']}: {n['fingerprint']}")
    print("Provisioning complete. Copy node directories to deployment USB drives.")


if __name__ == "__main__":
    main()
