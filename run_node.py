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

# Ensure project root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from transport.tcp import TCPTransport
from sync.node import Node
from crypto.keyring import NodeKeyring
from allocation.escrow import EscrowManager, InsufficientQuotaError
from allocation.tokens import TokenManager, UnauthorizedAllocationError


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
    if args.passphrase:
        keyring = NodeKeyring(node_id=args.id, passphrase=args.passphrase)

    node = Node(node_id=args.id, db_path=db_path, transport=transport, keyring=keyring)

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

            else:
                print(f"Unknown command: '{cmd}'. Type 'help' for available commands.")

    finally:
        print("\nShutting down TCP server...")
        transport.close()
        node.close()
        print("Node offline.")


if __name__ == "__main__":
    main()
