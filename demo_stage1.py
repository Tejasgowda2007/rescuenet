"""
RescueNet Stage 1 Demonstration:
Offline Event Log, SQLite Storage, and Materialized Current State.

Run this script to see:
1. Events being logged into an append-only SQLite database.
2. The Version Vector being calculated.
3. Materialized state being derived purely from history.
4. Conflict detection preserving conflicting updates (zero lost updates).
"""

import os
import sys
import time

# Ensure project root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from events.event import Event
from storage.sqlite_store import SQLiteEventStore
from storage.projector import StateProjector


def main():
    print("=" * 70)
    print(" RescueNet: Offline-First Disaster Coordination System (Stage 1)")
    print("=" * 70)

    # Step 1: Initialize local SQLite database
    db_file = "demo_node_alpha.db"
    if os.path.exists(db_file):
        os.remove(db_file)

    store = SQLiteEventStore(db_file)
    print(f"\n[1] Initialized append-only event store at: {db_file}")

    # Step 2: Simulate volunteer activity on Device Alpha
    now = time.time()
    events = [
        Event(
            node_id="device-alpha",
            counter=1,
            timestamp=now - 300,
            entity_type="shelter",
            entity_id="shelter-st-jude",
            operation="CREATE",
            payload={"name": "St. Jude Community Hall", "capacity": 200, "occupancy": 0, "status": "OPEN"},
        ),
        Event(
            node_id="device-alpha",
            counter=2,
            timestamp=now - 200,
            entity_type="supply",
            entity_id="supply-water-c1",
            operation="CREATE",
            payload={"item": "Clean Water (1L Bottles)", "quantity": 1200, "unit": "bottles"},
        ),
        Event(
            node_id="device-alpha",
            counter=3,
            timestamp=now - 150,
            entity_type="person",
            entity_id="person-david-k",
            operation="CREATE",
            payload={"name": "David Kim", "status": "MISSING", "last_seen": "Bridge Rd & 4th Ave"},
        ),
        Event(
            node_id="device-beta",  # Received during earlier sync from peer Beta
            counter=1,
            timestamp=now - 100,
            entity_type="person",
            entity_id="person-david-k",
            operation="UPDATE",
            payload={"status": "FOUND_SAFE", "current_location": "St. Jude Shelter"},
        ),
        Event(
            node_id="device-alpha",
            counter=4,
            timestamp=now - 50,
            entity_type="shelter",
            entity_id="shelter-st-jude",
            operation="UPDATE",
            payload={"occupancy": 45},
        ),
    ]

    print("\n[2] Logging 5 disaster events to SQLite:")
    for ev in events:
        newly_added = store.append(ev)
        print(f"  + Event {ev.counter} from {ev.node_id:12} | {ev.operation:7} {ev.entity_type:8} "
              f"({ev.entity_id}) -> Stored? {newly_added}")

    # Step 3: Inspect Version Vector
    vv = store.get_version_vector()
    print(f"\n[3] Local Version Vector: {vv}")
    print("    Explanation: device-alpha has seen up to counter 4 for itself, and 1 from device-beta.")

    # Step 4: Compute Current Materialized State from raw events
    projector = StateProjector()
    all_events = store.get_all_events()
    state = projector.compute_state(all_events)

    print("\n[4] Computed Materialized State (derived purely from log replay):")
    print("\n  --- SHELTERS ---")
    for s_id, s_data in state["shelter"].items():
        print(f"  * [{s_id}] {s_data['name']} (Occupancy: {s_data['occupancy']}/{s_data['capacity']})")

    print("\n  --- SUPPLIES ---")
    for sp_id, sp_data in state["supply"].items():
        print(f"  * [{sp_id}] {sp_data['item']}: {sp_data['quantity']} {sp_data['unit']}")

    print("\n  --- PEOPLE (Conflict-Aware) ---")
    for p_id, p_data in state["person"].items():
        print(f"  * [{p_id}] {p_data['name']} -> Current Status: {p_data['status']}")
        if p_data.get("conflicts"):
            print(f"    ! [CONFLICT FLAGGED FOR HUMAN REVIEW]:")
            for c in p_data["conflicts"]:
                print(f"      - Reported by {c['node_id']}: changed '{c['previous_status']}' -> '{c['conflicting_status']}'")

    # Step 5: Verify Append-Only Immutability
    print(f"\n[5] Database verification:")
    print(f"  Total raw events in SQLite log: {store.count()}")
    print("  Notice: nothing was overwritten. Historical states remain intact in SQLite.")

    store.close()
    if os.path.exists(db_file):
        os.remove(db_file)
    print("\n[OK] Stage 1 demo completed successfully!\n")


if __name__ == "__main__":
    main()
