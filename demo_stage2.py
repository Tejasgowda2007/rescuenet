"""
RescueNet Stage 2 Demonstration:
Version-Vector Anti-Entropy Sync between In-Memory Nodes with Byte Counting.

Run this script to see:
1. Two volunteer devices operating completely offline in separate disaster zones.
2. The devices meeting and performing bi-directional anti-entropy sync.
3. Exact wire bytes counted and reported for the exchange.
4. Mathematical convergence to identical state on both devices.
5. Zero payload overhead on follow-up sync when already up-to-date.
"""

import os
import sys

# Ensure project root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from transport.in_memory import InMemoryTransport
from sync.node import Node


def print_separator(title: str):
    print("\n" + "=" * 70)
    print(f" {title}")
    print("=" * 70)


def main():
    print_separator("RescueNet: Stage 2 Anti-Entropy Sync with Byte Counting")

    # Step 1: Initialize transport and two volunteer nodes
    transport = InMemoryTransport()
    node_alpha = Node("volunteer-alpha", ":memory:", transport)
    node_beta = Node("volunteer-beta", ":memory:", transport)

    print("\n[1] Deployed two volunteer devices:")
    print("    * Device Alpha: Search & Rescue Team (North Sector)")
    print("    * Device Beta:  Field Medical Tent (South Sector)")

    # Step 2: Offline work (No internet, completely partitioned)
    print_separator("Step 2: Isolated Offline Data Entry")

    print("[Alpha] Recording events locally:")
    e1 = node_alpha.record_event(
        "shelter", "shelter-gym", "CREATE",
        {"name": "East High Gym", "capacity": 250, "status": "OPEN"}
    )
    e2 = node_alpha.record_event(
        "supply", "blankets-01", "CREATE",
        {"item": "Wool Blankets", "quantity": 150, "unit": "pieces"}
    )
    e3 = node_alpha.record_event(
        "person", "person-lucas", "CREATE",
        {"name": "Lucas Vance", "status": "MISSING", "age": 8}
    )
    print(f"  + Alpha logged: {e1.entity_id} ({e1.operation})")
    print(f"  + Alpha logged: {e2.entity_id} ({e2.operation})")
    print(f"  + Alpha logged: {e3.entity_id} ({e3.operation})")

    print("\n[Beta] Recording events locally:")
    e4 = node_beta.record_event(
        "need", "need-oxygen", "CREATE",
        {"item": "O2 Cylinders", "urgency": "CRITICAL", "qty": 5}
    )
    e5 = node_beta.record_event(
        "person", "person-lucas", "UPDATE",
        {"status": "FOUND_SAFE", "current_location": "Field Medical Tent"}
    )
    print(f"  + Beta logged:  {e4.entity_id} ({e4.operation})")
    print(f"  + Beta logged:  {e5.entity_id} ({e5.operation})")

    print("\nPre-Sync Status:")
    print(f"  Alpha Event Count: {node_alpha.store.count()} | Version Vector: {node_alpha.get_version_vector()}")
    print(f"  Beta  Event Count: {node_beta.store.count()} | Version Vector: {node_beta.get_version_vector()}")

    # Step 3: Volunteers meet at Base Camp and sync
    print_separator("Step 3: Direct Peer-to-Peer Anti-Entropy Sync")
    print("[Sync] Alpha initiates sync with Beta via transport...")

    stats = node_alpha.sync_with("volunteer-beta")

    print("\n[Sync Telemetry & Byte Counting]:")
    print(f"  * Status:           {'SUCCESS' if stats.success else 'FAILED'}")
    print(f"  * Events Sent:      {stats.events_sent} events (Alpha -> Beta)")
    print(f"  * Events Received:  {stats.events_received} events (Beta -> Alpha)")
    print(f"  * Bytes Sent:       {stats.bytes_sent} bytes (wire payload)")
    print(f"  * Bytes Received:   {stats.bytes_received} bytes (wire payload)")
    print(f"  * Total Wire Size:  {stats.total_bytes} bytes exchanged")

    # Step 4: Verify Convergence
    print_separator("Step 4: Post-Sync State Convergence Check")
    vv_alpha = node_alpha.get_version_vector()
    vv_beta = node_beta.get_version_vector()

    print(f"Alpha Version Vector: {vv_alpha}")
    print(f"Beta  Version Vector: {vv_beta}")
    assert vv_alpha == vv_beta, "Version vectors must be identical!"

    state_alpha = node_alpha.get_state()
    state_beta = node_beta.get_state()
    assert state_alpha == state_beta, "States must be 100% converged!"

    print("\nState converged on both devices:")
    print("  * Shelters:     ", list(state_alpha["shelter"].keys()))
    print("  * Supplies:     ", list(state_alpha["supply"].keys()))
    print("  * Needs:        ", list(state_alpha["need"].keys()))
    print("  * People:       ", list(state_alpha["person"].keys()))

    lucas = state_alpha["person"]["person-lucas"]
    print(f"\n  Person 'Lucas Vance' status: {lucas['status']} at {lucas.get('current_location')}")
    print(f"  Conflict ledger count: {len(lucas['conflicts'])} (Zero lost updates!)")

    # Step 5: Verify Efficiency of Subsequent Sync (Requirement 4)
    print_separator("Step 5: Immediate Follow-up Sync (Testing Minimal Payloads)")
    print("[Sync] Alpha initiates second sync with Beta immediately...")

    stats_repeat = node_alpha.sync_with("volunteer-beta")

    print(f"  * Events Sent:      {stats_repeat.events_sent} (Expected 0)")
    print(f"  * Events Received:  {stats_repeat.events_received} (Expected 0)")
    print(f"  * Total Wire Bytes: {stats_repeat.total_bytes} bytes (handshake metadata only)")
    print(f"  * Bandwidth saved:  {stats.total_bytes - stats_repeat.total_bytes} bytes")

    # Step 6: Network Partition Simulation
    print_separator("Step 6: Network Split Simulation")
    print("[Partition] Simulating mountain pass blocking radio link between Alpha and Beta...")
    transport.cut_link("volunteer-alpha", "volunteer-beta")

    node_alpha.record_event("need", "need-fuel", "CREATE", {"item": "Diesel", "liters": 100})
    split_stats = node_alpha.sync_with("volunteer-beta")

    print(f"  * Sync during cut:  {'SUCCESS' if split_stats.success else 'FAILED'}")
    print(f"  * Error reported:   {split_stats.error}")

    print("\n[Heal] Radio link restored. Re-syncing...")
    transport.heal_link("volunteer-alpha", "volunteer-beta")
    heal_stats = node_alpha.sync_with("volunteer-beta")
    print(f"  * Sync after heal:  {'SUCCESS' if heal_stats.success else 'FAILED'}")
    print(f"  * Delta sync sent:  {heal_stats.events_sent} event(s) across healed link")

    # Clean up
    node_alpha.close()
    node_beta.close()
    print("\n[OK] Stage 2 demonstration finished successfully!\n")


if __name__ == "__main__":
    main()
