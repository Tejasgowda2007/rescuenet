"""
RescueNet Stage 7 Demonstration:
Three-Node Real TCP Transport Sync (Hotspot / Local Wi-Fi with Internet Off).

Run this script to see:
1. Three standalone disaster coordination nodes bound to actual TCP ports (8001, 8002, 8003).
2. Point-to-point stream framing with 4-byte length prefixes over real IP sockets.
3. Isolated offline entries on each laptop.
4. Transitive mesh synchronization over TCP without any central server or internet.
5. Verification of 100% state convergence across the TCP network.
"""

import os
import sys
import time

# Ensure project root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from transport.tcp import TCPTransport
from sync.node import Node
from allocation.escrow import EscrowManager
from allocation.tokens import TokenManager


def print_banner(text: str):
    print("\n" + "=" * 76)
    print(f" {text}")
    print("=" * 76)


def main():
    print_banner("RescueNet Stage 7: Real TCP Socket Transport (Hotspot Mesh)")

    ports = {"alpha": 8001, "beta": 8002, "gamma": 8003}

    print("\n[1] Initializing 3 TCP Sockets (simulating 3 laptops on a Wi-Fi hotspot):")
    transports = {}
    nodes = {}

    for name, port in ports.items():
        t = TCPTransport(node_id=f"laptop-{name}", host="127.0.0.1", port=port)
        transports[name] = t
        n = Node(f"laptop-{name}", ":memory:", t)
        nodes[name] = n
        print(f"    * laptop-{name:<6} listening on TCP 127.0.0.1:{t.port}")

    # Build full mesh peer directory
    print("\n[2] Configuring local mesh peer routing table:")
    for src_name, src_t in transports.items():
        for dest_name, dest_t in transports.items():
            if src_name != dest_name:
                src_t.add_peer(f"laptop-{dest_name}", "127.0.0.1", dest_t.port)
        print(f"    laptop-{src_name} peers: {list(src_t.peers.keys())}")

    # -------------------------------------------------------------
    # ISOLATED OFFLINE DATA ENTRY (NO COMMUNICATION YET)
    # -------------------------------------------------------------
    print_banner("Step 3: Disconnected Field Data Entry on Each Laptop")

    print("[Laptop Alpha - Rescue Squad 1]:")
    e1 = nodes["alpha"].record_event(
        "shelter", "shelter-school", "CREATE",
        {"name": "Roosevelt Middle School Gym", "capacity": 200, "status": "OPEN"}
    )
    EscrowManager.create_pool(
        node=nodes["alpha"],
        supply_id="mre-pool",
        item_name="MRE Field Rations",
        total_quantity=90,
        initial_quotas={"laptop-alpha": 30, "laptop-beta": 30, "laptop-gamma": 30},
        unit="meals",
    )
    print("  + Logged shelter: Roosevelt Middle School (200 cap)")
    print("  + Created MRE escrow pool: 90 meals (30 per laptop allowance)")

    print("\n[Laptop Beta - Medical Field Tent]:")
    nodes["beta"].record_event(
        "person", "person-samuel", "CREATE",
        {"name": "Samuel Jackson", "status": "FOUND_SAFE", "location": "Field Tent Beta"}
    )
    nodes["beta"].record_event(
        "need", "need-insulin", "CREATE",
        {"item": "Rapid Insulin 100IU", "urgency": "CRITICAL", "qty": 10}
    )
    print("  + Logged person found: Samuel Jackson (FOUND_SAFE)")
    print("  + Logged critical need: Rapid Insulin")

    print("\n[Laptop Gamma - Coast Guard Station]:")
    TokenManager.register_item(
        node=nodes["gamma"],
        item_id="boat-zodiac",
        item_name="Zodiac Hurricane Evacuation Boat",
        initial_holder_id="laptop-gamma",
        location="Pier 7",
    )
    print("  + Registered indivisible scarce asset: Zodiac Hurricane Boat (Token held by laptop-gamma)")

    print("\nPre-Sync Status:")
    for name, n in nodes.items():
        print(f"  laptop-{name:<6} | Events: {n.store.count()} | Version Vector: {n.get_version_vector()}")

    # -------------------------------------------------------------
    # REAL TCP SYNCHRONIZATION OVER LOOPBACK SOCKETS
    # -------------------------------------------------------------
    print_banner("Step 4: Real-Time Peer-to-Peer TCP Synchronization")
    print("Volunteers connect laptops to the same Wi-Fi hotspot (Internet OFF).")
    print("Initiating streaming TCP socket sync sessions:\n")

    # Sync Alpha -> Beta
    print("[TCP 8001 -> 8002] laptop-alpha syncs with laptop-beta...")
    s1 = nodes["alpha"].sync_with("laptop-beta")
    print(f"  -> {s1.summary()}")

    # Sync Beta -> Gamma
    print("\n[TCP 8002 -> 8003] laptop-beta syncs with laptop-gamma...")
    s2 = nodes["beta"].sync_with("laptop-gamma")
    print(f"  -> {s2.summary()}")

    # Sync Gamma -> Alpha
    print("\n[TCP 8003 -> 8001] laptop-gamma syncs with laptop-alpha...")
    s3 = nodes["gamma"].sync_with("laptop-alpha")
    print(f"  -> {s3.summary()}")

    # Final transitive sweep to close 3-node cycle
    print("\n[TCP Final Sweep] laptop-alpha syncs with laptop-beta to complete transitive gossip...")
    s4 = nodes["alpha"].sync_with("laptop-beta")
    print(f"  -> {s4.summary()}")

    # -------------------------------------------------------------
    # CONVERGENCE VERIFICATION OVER TCP
    # -------------------------------------------------------------
    print_banner("Step 5: Post-Sync Convergence Verification Across Real TCP Sockets")

    first_vv = nodes["alpha"].get_version_vector()
    first_state = nodes["alpha"].get_state()
    converged = True

    for name, n in nodes.items():
        vv = n.get_version_vector()
        state = n.get_state()
        print(f"  laptop-{name:<6} | Events: {n.store.count()} | Version Vector: {vv}")
        if vv != first_vv or state != first_state:
            converged = False

    print("\n[TCP Wire Bandwidth Telemetry]:")
    total_wire = sum(t.get_stats()["total_bytes"] for t in transports.values())
    for name, t in transports.items():
        stats = t.get_stats()
        print(f"  laptop-{name:<6} socket: {stats['total_bytes']} bytes ({stats['total_messages']} frames)")
    print(f"  Total Network Wire Bytes Exchanged: {total_wire} bytes")

    print("\n[Convergence Result]:")
    print(f"  Status: {'PASSED (100% CONVERGED OVER TCP)' if converged else 'FAILED'}")
    print("  Shared Entities Active:")
    print("    * Shelters:     ", list(first_state["shelter"].keys()))
    print("    * Supplies:     ", list(first_state["supply"].keys()))
    print("    * Needs:        ", list(first_state["need"].keys()))
    print("    * People:       ", list(first_state["person"].keys()))
    print("    * Scarce Items: ", list(first_state["scarce_item"].keys()))

    # Clean shutdown of all TCP listeners
    print("\n[Cleanup] Shutting down all TCP socket listeners...")
    for t in transports.values():
        t.close()
    for n in nodes.values():
        n.close()

    print("\n[OK] Stage 7 real TCP transport demonstration completed successfully!\n")


if __name__ == "__main__":
    main()
