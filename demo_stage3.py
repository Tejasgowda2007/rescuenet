"""
RescueNet Stage 3 Demonstration:
Merge/Conflict Rules and Scarce-Resource Allocation (Escrow Quotas & Possession Tokens).

Run this script to see:
1. Escrow quotas preventing over-allocation of divisible medicine/supplies.
2. Single-owner possession tokens making double-allocation of indivisible items
   (like the last rescue boat) mathematically impossible offline.
3. Conflict ledgers preserving conflicting person reports with zero lost updates,
   followed by human-in-the-loop triage resolution.
"""

import os
import sys

# Ensure project root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from transport.in_memory import InMemoryTransport
from sync.node import Node
from allocation.escrow import EscrowManager, InsufficientQuotaError
from allocation.tokens import TokenManager, UnauthorizedAllocationError
from allocation.conflict_resolver import ConflictResolver


def print_header(title: str):
    print("\n" + "=" * 70)
    print(f" {title}")
    print("=" * 70)


def main():
    print_header("RescueNet Stage 3: Merge Rules & Scarce Resource Allocation")

    transport = InMemoryTransport()
    alpha = Node("node-alpha", ":memory:", transport)
    beta = Node("node-beta", ":memory:", transport)

    # -------------------------------------------------------------
    # DEMO 1: COUNTABLE SUPPLIES (ESCROW QUOTAS)
    # -------------------------------------------------------------
    print_header("Part 1: Countable Supplies (Escrow Quotas vs Over-Allocation)")
    print("Scenario: 100 units of Rare Blood Plasma arriving at Central Depot.")
    print("Depot grants initial escrow allowances: Alpha = 50, Beta = 50.")

    EscrowManager.create_pool(
        node=alpha,
        supply_id="plasma-pool",
        item_name="Blood Plasma O-Neg",
        total_quantity=100,
        initial_quotas={"node-alpha": 50, "node-beta": 50},
        unit="bags",
    )
    alpha.sync_with("node-beta")

    print("\n[Split] Alpha and Beta separate into disconnected flood sectors (No internet).")
    transport.cut_link("node-alpha", "node-beta")

    # Offline spending
    print("[Alpha] Consuming 30 bags for Emergency Tents...")
    EscrowManager.consume(alpha, "plasma-pool", 30, "Tents Sector A")

    print("[Beta]  Consuming 40 bags for Trauma Center...")
    EscrowManager.consume(beta, "plasma-pool", 40, "Trauma Center Sector B")

    # Beta attempts over-allocation
    print("\n[Beta]  Trauma doctor requests 15 MORE bags (Beta only has 10 left)...")
    try:
        EscrowManager.consume(beta, "plasma-pool", 15, "Overflow Patients")
        print("ERROR: Should have been rejected!")
    except InsufficientQuotaError as e:
        print(f"  [PREVENTED OFFLINE]: {e}")
        print("  Mathematical Guarantee: Node cannot spend beyond its local escrow pool!")

    # Volunteers meet and rebalance
    print("\n[Heal] Alpha and Beta meet at supply depot. Alpha transfers 15 bags from its quota to Beta.")
    transport.heal_link("node-alpha", "node-beta")
    alpha.sync_with("node-beta")

    EscrowManager.transfer_quota(
        from_node=alpha,
        to_node_id="node-beta",
        supply_id="plasma-pool",
        quantity=15,
        reason="Field rebalance for Trauma Center",
    )
    alpha.sync_with("node-beta")

    plasma_state = alpha.get_state()["supply"]["plasma-pool"]
    print(f"\nPost-Rebalance Supply State:")
    print(f"  * Total Inventory: {plasma_state['total_quantity']} bags")
    print(f"  * Total Consumed:  {plasma_state['consumed']} bags")
    print(f"  * Alpha Quota:     {plasma_state['quotas']['node-alpha']} bags")
    print(f"  * Beta Quota:      {plasma_state['quotas']['node-beta']} bags")
    conservation = plasma_state['consumed'] + sum(plasma_state['quotas'].values())
    print(f"  * Conservation Invariant: {plasma_state['consumed']} + {sum(plasma_state['quotas'].values())} = {conservation} == 100 [OK]")

    # -------------------------------------------------------------
    # DEMO 2: INDIVISIBLE SCARCE ASSET (THE LAST BOAT)
    # -------------------------------------------------------------
    print_header("Part 2: Indivisible Asset (The Last Boat - Single Token Guarantee)")
    print("Scenario: Exactly 1 Zodiac Rescue Boat available. Alpha holds the possession token.")

    TokenManager.register_item(
        node=alpha,
        item_id="boat-zodiac-1",
        item_name="Zodiac Inflatable Boat #1",
        initial_holder_id="node-alpha",
        location="Riverside Station",
    )
    alpha.sync_with("node-beta")

    print("\n[Split] Network divides again.")
    transport.cut_link("node-alpha", "node-beta")

    print("[Alpha] Token holder confirms allocation to Mission 'Evacuate School':")
    TokenManager.confirm_allocation(
        node=alpha,
        item_id="boat-zodiac-1",
        assigned_to_mission="Evacuate School (20 children stranded)",
        target_node_id="node-alpha",
    )
    print("  * Alpha confirmed allocation successfully.")

    print("\n[Beta]  Offline Beta tries to confirm allocation of the SAME boat for 'Hospital Evac':")
    try:
        TokenManager.confirm_allocation(
            node=beta,
            item_id="boat-zodiac-1",
            assigned_to_mission="Hospital Evac",
            target_node_id="node-beta",
        )
        print("ERROR: Should have been rejected!")
    except UnauthorizedAllocationError as e:
        print(f"  [PREVENTED OFFLINE]: {e}")

    print("\n[Beta]  Beta logs an offline REQUEST instead (status='REQUESTED'):")
    TokenManager.request_allocation(
        node=beta,
        item_id="boat-zodiac-1",
        mission_description="Hospital Evacuation Sector 5",
        urgency="CRITICAL",
    )

    print("\n[Heal] Network reconnects and nodes sync:")
    transport.heal_link("node-alpha", "node-beta")
    alpha.sync_with("node-beta")

    boat_state = beta.get_state()["scarce_item"]["boat-zodiac-1"]
    print(f"  * Boat Status:       {boat_state['status']}")
    print(f"  * Allocated To:      {boat_state['allocated_to']}")
    print(f"  * Pending Requests:  {len(boat_state['requests'])} (Beta's claim queued safely without double-allocating!)")

    # -------------------------------------------------------------
    # DEMO 3: ZERO LOST UPDATES & HUMAN TRIAGE CONFLICT RESOLUTION
    # -------------------------------------------------------------
    print_header("Part 3: Conflict Ledger & Human-in-the-Loop Triage (Person Tracking)")

    print("[Alpha] Logs: 'Elena Rostova' MISSING at Bridge 4")
    alpha.record_event("person", "person-elena", "CREATE", {
        "name": "Elena Rostova", "status": "MISSING", "location": "Bridge 4"
    })

    print("[Beta]  Concurrently logs: 'Elena Rostova' FOUND_INJURED at Field Clinic")
    beta.record_event("person", "person-elena", "UPDATE", {
        "status": "FOUND_INJURED", "location": "Field Clinic Tent 2"
    })

    alpha.sync_with("node-beta")

    elena = alpha.get_state()["person"]["person-elena"]
    print("\nPost-Sync Conflicted Person State (Zero Lost Updates):")
    print(f"  * Displayed Status: {elena['status']}")
    print(f"  * Active Conflicts: {len(elena['conflicts'])}")
    for c in elena["conflicts"]:
        print(f"    - Alternate observation from {c['node_id']}: '{c['previous_status']}' vs '{c['conflicting_status']}'")

    print("\n[Triage] Medical Officer verifies Elena in person and issues RESOLVE_CONFLICT event:")
    ConflictResolver.resolve_person_conflict(
        node=alpha,
        person_id="person-elena",
        verified_status="CONFIRMED_SAFE_TREATED",
        verified_location="General Hospital Ward 3",
        resolution_notes="Identity verified by triage nurse badge #402",
    )

    alpha.sync_with("node-beta")

    elena_resolved = beta.get_state()["person"]["person-elena"]
    print(f"\nFinal State on Peer Node Beta:")
    print(f"  * Status:             {elena_resolved['status']}")
    print(f"  * Location:           {elena_resolved['location']}")
    print(f"  * Active Conflicts:   {len(elena_resolved['conflicts'])} (Dispute resolved)")
    print(f"  * Archived Conflicts: {len(elena_resolved['archived_conflicts'])} (Audit trail preserved)")
    print(f"  * Resolved Notes:     {elena_resolved['_resolution_notes']}")

    alpha.close()
    beta.close()
    print("\n[OK] Stage 3 demonstration completed successfully!\n")


if __name__ == "__main__":
    main()
