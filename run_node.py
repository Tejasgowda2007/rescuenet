"""
RescueNet Standalone Node CLI Runner for Real Laptops over Local Wi-Fi / Hotspot.

Usage Examples:
---------------
Run 3 instances on one machine (or 3 real laptops on a Wi-Fi hotspot):

Terminal 1 (Laptop Alpha):
  python run_node.py --id alpha --port 8001 --peers beta=127.0.0.1:8002,gamma=127.0.0.1:8003 --db alpha.db

Terminal 2 (Laptop Beta):
  python run_node.py --id beta --port 8002 --peers alpha=127.0.0.1:8001,gamma=127.0.0.1:8003 --db beta.db

Terminal 3 (Laptop Gamma):
  python run_node.py --id gamma --port 8003 --peers alpha=127.0.0.1:8001,beta=127.0.0.1:8002 --db gamma.db

For real laptops on a Wi-Fi router (no internet):
  Use your laptop's local IP (e.g. 192.168.1.X) and pass `--host 0.0.0.0`.
"""

from __future__ import annotations
import argparse
import sys
import os
import shlex
import json

# Ensure project root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from transport.tcp import TCPTransport
from sync.node import Node
from crypto.keyring import NodeKeyring
from allocation.escrow import EscrowManager, InsufficientQuotaError
from allocation.tokens import TokenManager, UnauthorizedAllocationError


class StrictSecurityError(Exception):
    """Raised when strict production security conditions are not satisfied."""
    pass


def validate_and_build_strict_keyring(
    node_id: str,
    key_dir: Optional[str],
    mesh_psk_hex: Optional[str],
    passphrase: Optional[str] = None,
) -> NodeKeyring:
    """
    Enforce strict production security initialization.
    Aborts startup if keys, manifests, or PSK are missing, invalid, or corrupted.
    Never silently falls back to unauthenticated operation.
    """
    if not key_dir:
        raise StrictSecurityError("Strict security requires --key-dir to be specified.")
    if not os.path.exists(key_dir):
        raise StrictSecurityError(f"Strict security key directory '{key_dir}' does not exist.")

    node_sec_dir = os.path.join(key_dir, node_id)
    if not os.path.exists(node_sec_dir):
        raise StrictSecurityError(f"Security directory for node '{node_id}' not found at '{node_sec_dir}'.")

    # 1. Verify identity key exists
    key_enc_file = os.path.join(node_sec_dir, "identity.key.enc")
    pub_file = os.path.join(node_sec_dir, "identity.pub")
    if not (os.path.exists(key_enc_file) and os.path.exists(pub_file)):
        raise StrictSecurityError(
            f"Local Ed25519 identity key missing for '{node_id}' in '{node_sec_dir}'. "
            "Run 'python -m scripts.provision_mesh_keys' first."
        )

    # 2. Verify Mesh PSK
    effective_psk_hex = mesh_psk_hex
    if not effective_psk_hex:
        # Check if mesh_config.json exists in node_sec_dir
        config_path = os.path.join(node_sec_dir, "mesh_config.json")
        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                    effective_psk_hex = cfg.get("mesh_psk_hex", "")
            except Exception as e:
                raise StrictSecurityError(f"Failed to read mesh_config.json: {e}") from e

    if not effective_psk_hex or len(effective_psk_hex.strip()) != 64:
        raise StrictSecurityError(
            "Strict security requires a valid 256-bit Mesh Pre-Shared Key (64 hex characters) via --mesh-psk or mesh_config.json."
        )

    try:
        mesh_key_bytes = bytes.fromhex(effective_psk_hex.strip())
        if len(mesh_key_bytes) != 32:
            raise ValueError()
    except Exception as e:
        raise StrictSecurityError("Invalid hexadecimal encoding in Mesh PSK.") from e

    # 3. Verify trusted peers manifest
    manifest_file = os.path.join(node_sec_dir, "trusted_peers.json")
    if not os.path.exists(manifest_file):
        raise StrictSecurityError(
            f"Trusted peer manifest missing at '{manifest_file}'. Cannot operate in zero-trust mode without peer manifest."
        )

    # 4. Initialize Keyring
    try:
        keyring = NodeKeyring(
            node_id=node_id,
            passphrase=passphrase if passphrase else None,
            keys_dir=key_dir,
            mesh_key=mesh_key_bytes,
        )
    except Exception as e:
        raise StrictSecurityError(f"Cryptographic initialization failed for '{node_id}': {e}") from e

    if keyring.private_key is None:
        raise StrictSecurityError(f"Failed to load private Ed25519 signing key for '{node_id}'.")
    if keyring.mesh_cipher is None:
        raise StrictSecurityError(f"Failed to activate MeshCipher for '{node_id}'.")
    if len(keyring.trusted_peers) == 0:
        raise StrictSecurityError(f"No trusted peers found in manifest for '{node_id}'.")

    return keyring


def parse_peers(peers_str: str) -> list[tuple[str, str, int]]:
    """Parse peer argument format: 'node_b=192.168.1.2:8002,node_c=192.168.1.3:8003'"""
    if not peers_str:
        return []
    result = []
    for item in peers_str.split(","):
        item = item.strip()
        if not item:
            continue
        peer_id, addr = item.split("=")
        host, port_str = addr.split(":")
        result.append((peer_id.strip(), host.strip(), int(port_str.strip())))
    return result


def main():
    parser = argparse.ArgumentParser(description="RescueNet Offline Disaster Node Runner")
    parser.add_argument("--id", required=True, help="Unique node identifier (e.g. alpha)")
    parser.add_argument("--host", default="0.0.0.0", help="Host interface to bind (default 0.0.0.0 for LAN)")
    parser.add_argument("--port", type=int, required=True, help="TCP port to listen on (e.g. 8001)")
    parser.add_argument("--peers", default="", help="Peers format: 'beta=127.0.0.1:8002,gamma=127.0.0.1:8003'")
    parser.add_argument("--db", default="", help="SQLite database path (default :memory: or node_<id>.db)")
    parser.add_argument("--passphrase", default="", help="Optional encryption passphrase for PII")
    parser.add_argument("--key-dir", default="", help="Optional persistent security directory (e.g. data/security)")
    parser.add_argument("--mesh-psk", default="", help="Optional 256-bit Mesh Pre-Shared Key (64-char hex string)")
    parser.add_argument("--enroll-peers", default="", help="Enroll peer public keys: 'beta=<pubkey_hex>,gamma=<pubkey_hex>'")
    parser.add_argument("--strict-security", action="store_true", help="Enforce strict production security: abort startup if keys, manifests, or PSK are missing")
    parser.add_argument("--web", action="store_true", help="Launch embedded web dashboard server on web-port")
    parser.add_argument("--web-port", type=int, default=8000, help="Web dashboard HTTP port (default 8000)")
    parser.add_argument("--discovery", action="store_true", default=True, help="Enable automatic UDP peer discovery (default True)")
    parser.add_argument("--no-discovery", dest="discovery", action="store_false", help="Disable automatic UDP peer discovery")
    parser.add_argument("--discovery-port", type=int, default=8002, help="UDP peer discovery port (default 8002)")
    parser.add_argument("--peer-file", default="peer_ips.txt", help="Path to peer configuration file (default peer_ips.txt)")

    args = parser.parse_args()

    db_path = args.db if args.db else f"node_{args.id}.db"

    # Step 1: Initialize TCP transport
    transport = TCPTransport(node_id=args.id, host=args.host, port=args.port)

    # Step 2: Register peers
    peers = parse_peers(args.peers)
    for peer_id, p_host, p_port in peers:
        transport.add_peer(peer_id, p_host, p_port)

    # Step 3: Initialize keyring & Node
    keyring = None
    if args.strict_security:
        try:
            keyring = validate_and_build_strict_keyring(
                node_id=args.id,
                key_dir=args.key_dir,
                mesh_psk_hex=args.mesh_psk,
                passphrase=args.passphrase,
            )
            print("  * [SECURITY] Strict production security active: Fail-Closed enforcement enabled.")
        except StrictSecurityError as e:
            print(f"\n[FATAL ERROR] {e}")
            transport.close()
            sys.exit(1)
    else:
        mesh_key_bytes = None
        if args.mesh_psk:
            try:
                mesh_key_bytes = bytes.fromhex(args.mesh_psk.strip())
            except ValueError:
                print("[WARN] Invalid --mesh-psk hex string; ignoring.")

        if args.passphrase or args.key_dir or mesh_key_bytes:
            keys_directory = args.key_dir if args.key_dir else None
            keyring = NodeKeyring(
                node_id=args.id,
                passphrase=args.passphrase if args.passphrase else None,
                keys_dir=keys_directory,
                mesh_key=mesh_key_bytes,
            )

            # Enroll any peers passed on CLI
            if args.enroll_peers:
                for item in args.enroll_peers.split(","):
                    if "=" in item:
                        p_id, p_pub = item.strip().split("=", 1)
                        try:
                            keyring.register_peer(p_id.strip(), p_pub.strip())
                            print(f"  * Enrolled peer '{p_id.strip()}' with public key.")
                        except Exception as e:
                            print(f"  [WARN] Failed to enroll '{p_id}': {e}")

    node = Node(
        node_id=args.id,
        db_path=db_path,
        transport=transport,
        keyring=keyring,
        strict_mode=args.strict_security,
    )

    # Load peer file if present
    if args.peer_file and os.path.exists(args.peer_file):
        try:
            with open(args.peer_file, "r", encoding="utf-8") as pf:
                for line in pf:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" in line:
                        p_id, addr = line.split("=", 1)
                        if ":" in addr:
                            ph, pp = addr.split(":", 1)
                            transport.add_peer(p_id.strip(), ph.strip(), int(pp.strip()))
                            print(f"  * Loaded peer '{p_id.strip()}' from {args.peer_file}")
        except Exception as e:
            print(f"  [WARN] Failed to read {args.peer_file}: {e}")

    # Start autonomous anti-entropy background gossip
    node.start_gossip(interval_sec=3.0)

    # Start UDP discovery beacon
    beacon = None
    if args.discovery:
        from transport.discovery import PeerDiscoveryBeacon
        def _on_discovered(p_id: str, p_host: str, p_port: int, p_web: int):
            transport.add_peer(p_id, p_host, p_port)
            if node.gossip_daemon:
                node.gossip_daemon.add_peer(p_id)
                node.gossip_daemon.wake_up()
            print(f"\n[DISCOVERY] Found peer '{p_id}' at {p_host}:{p_port}")

        beacon = PeerDiscoveryBeacon(
            node_id=args.id,
            tcp_port=transport.port,
            web_port=args.web_port if args.web else 0,
            broadcast_port=args.discovery_port,
            on_peer_discovered=_on_discovered,
        )
        beacon.start()
        print(f"  * UDP Peer Discovery:  Active on port {args.discovery_port}")

    # Start embedded web server if requested
    if args.web:
        import threading
        import uvicorn
        from api.node_server import RescueNetNodeService, create_app

        service = RescueNetNodeService(
            node_id=args.id,
            host=args.host,
            tcp_port=transport.port,
            web_port=args.web_port,
            db_path=db_path,
            security_dir=args.key_dir,
            mesh_psk_hex=args.mesh_psk,
            passphrase=args.passphrase,
            strict_security=args.strict_security,
            enable_discovery=False,  # Already running beacon above
        )
        web_app = create_app(service)

        def _run_web():
            uvicorn.run(web_app, host=args.host, port=args.web_port, log_level="warning")

        t_web = threading.Thread(target=_run_web, name="WebDashboardServer", daemon=True)
        t_web.start()
        print(f"  * Web Dashboard:       http://{args.host}:{args.web_port}/")

    print("\n" + "=" * 70)
    print(f" RescueNet Node '{args.id}' Online (TCP Transport)")
    print("=" * 70)
    print(f"  * Listening Address:   {args.host}:{transport.port}")
    print(f"  * Database:            {db_path}")
    print(f"  * Registered Peers:    {list(transport.peers.keys())}")
    print(f"  * Initial Version:     {node.get_version_vector()}")
    print("Type 'help' for commands, 'exit' to quit.\n")

    try:
        while True:
            try:
                line = input(f"[{args.id}]> ").strip()
            except (EOFError, KeyboardInterrupt):
                break

            if not line:
                continue

            parts = shlex.split(line)
            cmd = parts[0].lower()

            if cmd in ("exit", "quit"):
                break

            elif cmd == "help":
                print("\nAvailable Commands:")
                print("  status                       - Show node status, version vector, and wire stats")
                print("  sync <peer_id>               - Perform anti-entropy sync with a peer")
                print("  sync-all                     - Sync with all registered peers")
                print("  state                        - Print current materialized domain state")
                print("  shelter <id> <name> <cap>    - Log shelter creation")
                print("  need <id> <item> <urgency>   - Log relief supply need")
                print("  person <id> <name> <status>  - Log missing or found person report")
                print("  add-peer <id> <host> <port>  - Dynamically add a new peer to route table")
                print("  fingerprint                  - Display local public key and cryptographic fingerprint")
                print("  enroll <id> <pubkey_hex>     - Enroll a trusted peer public key")
                print("  revoke <id>                  - Revoke/blacklist a compromised peer")
                print("  exit                         - Shutdown node cleanly\n")

            elif cmd == "status":
                stats = transport.get_stats()
                print(f"  Node ID:         {args.id}")
                print(f"  Listening:       {args.host}:{transport.port}")
                print(f"  Events Logged:   {node.store.count()}")
                print(f"  Version Vector:  {node.get_version_vector()}")
                print(f"  Peers Directory: {transport.peers}")
                print(f"  Wire Bytes:      {stats['total_bytes']} bytes ({stats['total_messages']} frames)")

            elif cmd == "sync":
                if len(parts) < 2:
                    print("Usage: sync <peer_id>")
                    continue
                target = parts[1]
                print(f"Initiating TCP sync with {target}...")
                sync_stats = node.sync_with(target)
                print(f"  Result: {sync_stats.summary()}")

            elif cmd == "sync-all":
                for p_id in list(transport.peers.keys()):
                    print(f"Syncing with {p_id}...")
                    res = node.sync_with(p_id)
                    print(f"  {p_id}: {res.summary()}")

            elif cmd == "state":
                state = node.get_state()
                print("\n--- CURRENT MATERIALIZED STATE ---")
                for category, items in state.items():
                    print(f"  [{category.upper()}] ({len(items)} records):")
                    for k, v in items.items():
                        print(f"    * {k}: {v}")
                print("----------------------------------\n")

            elif cmd == "shelter":
                if len(parts) < 4:
                    print("Usage: shelter <id> <name> <capacity>")
                    continue
                sid, sname, scap = parts[1], parts[2], int(parts[3])
                node.record_event("shelter", sid, "CREATE", {"name": sname, "capacity": scap, "occupancy": 0})
                print(f"[OK] Logged shelter '{sname}' ({scap} capacity)")

            elif cmd == "need":
                if len(parts) < 4:
                    print("Usage: need <id> <item> <urgency>")
                    continue
                nid, item, urg = parts[1], parts[2], parts[3]
                node.record_event("need", nid, "CREATE", {"item": item, "urgency": urg.upper()})
                print(f"[OK] Logged need '{item}' ({urg.upper()})")

            elif cmd == "person":
                if len(parts) < 4:
                    print("Usage: person <id> <name> <status>")
                    continue
                pid, pname, pstatus = parts[1], parts[2], parts[3]
                node.record_event("person", pid, "UPDATE", {"name": pname, "status": pstatus.upper()})
                print(f"[OK] Logged person '{pname}' status as {pstatus.upper()}")

            elif cmd == "add-peer":
                if len(parts) < 4:
                    print("Usage: add-peer <id> <host> <port>")
                    continue
                pid, phost, pport = parts[1], parts[2], int(parts[3])
                transport.add_peer(pid, phost, pport)
                print(f"[OK] Added peer '{pid}' at {phost}:{pport}")

            elif cmd == "fingerprint":
                if keyring:
                    from crypto.peer_manifest import compute_key_fingerprint
                    fp = compute_key_fingerprint(keyring.public_key_hex)
                    print(f"  Node ID:     {args.id}")
                    print(f"  Public Key:  {keyring.public_key_hex}")
                    print(f"  Fingerprint: {fp}")
                    print(f"  Trusted:     {list(keyring.trusted_peers.keys())}")
                    print(f"  Revoked:     {list(keyring.revoked_peers)}")
                else:
                    print("Keyring not active on this node. (Pass --key-dir or --passphrase)")

            elif cmd == "enroll":
                if len(parts) < 3:
                    print("Usage: enroll <peer_id> <public_key_hex>")
                    continue
                if not keyring:
                    print("Keyring not active. Cannot enroll peers.")
                    continue
                p_id, p_hex = parts[1], parts[2]
                try:
                    keyring.register_peer(p_id, p_hex)
                    print(f"[OK] Enrolled peer '{p_id}'")
                except Exception as e:
                    print(f"[ERROR] Enrollment failed: {e}")

            elif cmd == "revoke":
                if len(parts) < 2:
                    print("Usage: revoke <peer_id>")
                    continue
                if not keyring:
                    print("Keyring not active. Cannot revoke peers.")
                    continue
                p_id = parts[1]
                keyring.revoke_peer(p_id, reason="CLI_REVOCATION")
                print(f"[OK] Revoked peer '{p_id}'. All future events will be dropped.")

            else:
                print(f"Unknown command: '{cmd}'. Type 'help' for available commands.")

    finally:
        print("\nShutting down node services...")
        if beacon:
            beacon.stop()
        transport.close()
        node.close()
        print("Node offline.")


if __name__ == "__main__":
    main()
