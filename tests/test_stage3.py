"""
Unit and Integration Tests for Stage 3:
Merge/Conflict Rules, Escrow Quotas, and Indivisible Scarce-Resource Token Allocation.
"""

import pytest
from transport.in_memory import InMemoryTransport
from sync.node import Node
from allocation.escrow import EscrowManager, InsufficientQuotaError
from allocation.tokens import TokenManager, UnauthorizedAllocationError
from allocation.conflict_resolver import ConflictResolver
from events.event import Event


def test_escrow_quota_conservation_and_offline_consumption():
    """
    Test countable scarce resource allocation:
    Invariant: Sum(quotas) + consumed == total_inventory at all times.
    """
    transport = InMemoryTransport()
    node_a = Node("node-A", ":memory:", transport)
    node_b = Node("node-B", ":memory:", transport)

    # Depot creates an escrow pool of 100 insulin vials (50 for A, 50 for B)
    EscrowManager.create_pool(
        node=node_a,
        supply_id="supply-insulin",
        item_name="Insulin 100IU",
        total_quantity=100,
        initial_quotas={"node-A": 50, "node-B": 50},
        unit="vials",
    )

    # Sync pool creation from A to B
    node_a.sync_with("node-B")

    # Now partition the network: A and B are in separate flooded sectors
    transport.cut_link("node-A", "node-B")

    # Node A consumes 20 vials offline
    EscrowManager.consume(node_a, "supply-insulin", 20, "Mobile Clinic Alpha")
    # Node B consumes 35 vials offline
    EscrowManager.consume(node_b, "supply-insulin", 35, "Shelter South")

    # Heal network and sync
    transport.heal_link("node-A", "node-B")
    node_a.sync_with("node-B")

    # Both nodes converge to identical escrow state
    state_a = node_a.get_state()["supply"]["supply-insulin"]
    state_b = node_b.get_state()["supply"]["supply-insulin"]

    assert state_a == state_b
    assert state_a["consumed"] == 55  # 20 + 35
    assert state_a["quotas"]["node-A"] == 30  # 50 - 20
    assert state_a["quotas"]["node-B"] == 15  # 50 - 35

    # Conservation Law: Total quantity is strictly preserved
    assert state_a["consumed"] + sum(state_a["quotas"].values()) == 100

    node_a.close()
    node_b.close()


def test_escrow_over_allocation_strictly_prevented():
    """
    Test that an offline node CANNOT allocate more than its granted escrow quota.
    """
    transport = InMemoryTransport()
    node_a = Node("node-A", ":memory:", transport)

    EscrowManager.create_pool(
        node=node_a,
        supply_id="supply-blood",
        item_name="O-Negative Blood Units",
        total_quantity=10,
        initial_quotas={"node-A": 10},
        unit="bags",
    )

    # Attempt to consume 11 units when only 10 exist
    with pytest.raises(InsufficientQuotaError):
        EscrowManager.consume(node_a, "supply-blood", 11, "Emergency Surgery")

    # Consume 10 (full allowance)
    EscrowManager.consume(node_a, "supply-blood", 10, "Emergency Surgery")

    # Attempt to consume 1 more -> strictly rejected
    with pytest.raises(InsufficientQuotaError):
        EscrowManager.consume(node_a, "supply-blood", 1, "Another Patient")

    node_a.close()


def test_escrow_quota_transfer_between_nodes():
    """
    Volunteers meet at a checkpoint and rebalance quotas:
    Node A transfers 20 units from its quota to Node B.
    """
    transport = InMemoryTransport()
    node_a = Node("node-A", ":memory:", transport)
    node_b = Node("node-B", ":memory:", transport)

    EscrowManager.create_pool(
        node=node_a,
        supply_id="supply-mre",
        item_name="Emergency Rations",
        total_quantity=100,
        initial_quotas={"node-A": 80, "node-B": 20},
    )
    node_a.sync_with("node-B")

    # Node A transfers 30 rations to Node B
    EscrowManager.transfer_quota(
        from_node=node_a,
        to_node_id="node-B",
        supply_id="supply-mre",
        quantity=30,
        reason="Node B entering heavily populated refugee camp",
    )

    node_a.sync_with("node-B")

    state = node_b.get_state()["supply"]["supply-mre"]
    assert state["quotas"]["node-A"] == 50  # 80 - 30
    assert state["quotas"]["node-B"] == 50  # 20 + 30

    node_a.close()
    node_b.close()


def test_indivisible_scarce_item_single_token_guarantee():
    """
    Requirement 3: A scarce item (e.g. the last boat) must NEVER be allocated twice.
    Only the token holder can confirm allocation. Non-holders cannot double-allocate.
    """
    transport = InMemoryTransport()
    node_a = Node("node-A", ":memory:", transport)
    node_b = Node("node-B", ":memory:", transport)

    # Register indivisible boat; Node A holds the initial possession token
    TokenManager.register_item(
        node=node_a,
        item_id="boat-01",
        item_name="Zodiac Inflatable Rescue Boat",
        initial_holder_id="node-A",
        location="Harbor Base",
    )
    node_a.sync_with("node-B")

    # Partition network
    transport.cut_link("node-A", "node-B")

    # Node A (token holder) confirms allocation for Sector 1
    TokenManager.confirm_allocation(
        node=node_a,
        item_id="boat-01",
        assigned_to_mission="Evacuate Elderly Center Sector 1",
        target_node_id="node-A",
    )

    # Node B (does NOT hold token) attempts to confirm allocation -> RAISED!
    with pytest.raises(UnauthorizedAllocationError):
        TokenManager.confirm_allocation(
            node=node_b,
            item_id="boat-01",
            assigned_to_mission="Hospital Evacuation Sector 5",
            target_node_id="node-B",
        )

    # Instead, Node B properly issues an offline REQUEST
    TokenManager.request_allocation(
        node=node_b,
        item_id="boat-01",
        mission_description="Hospital Evacuation Sector 5",
        urgency="CRITICAL",
    )

    # Heal network and sync
    transport.heal_link("node-A", "node-B")
    node_a.sync_with("node-B")

    # Verify converged state
    boat_state = node_b.get_state()["scarce_item"]["boat-01"]
    assert boat_state["status"] == "CONFIRMED_ALLOCATED"
    assert boat_state["allocated_to"] == "Evacuate Elderly Center Sector 1"
    # Node B's request is recorded safely as a pending claim, avoiding double-allocation
    assert len(boat_state["requests"]) == 1
    assert boat_state["requests"][0]["node_id"] == "node-B"

    node_a.close()
    node_b.close()


def test_token_transfer_and_release():
    """
    Test passing token ownership and releasing an asset back to service.
    """
    transport = InMemoryTransport()
    node_a = Node("node-A", ":memory:", transport)
    node_b = Node("node-B", ":memory:", transport)

    TokenManager.register_item(
        node=node_a,
        item_id="gen-50kw",
        item_name="50kW Diesel Generator",
        initial_holder_id="node-A",
    )
    node_a.sync_with("node-B")

    # Node A hands off custody to Node B
    TokenManager.transfer_token(node_a, "gen-50kw", "node-B", reason="Field Hospital Setup")
    node_a.sync_with("node-B")

    # Node B is now verified token holder and allocates it
    TokenManager.confirm_allocation(
        node=node_b,
        item_id="gen-50kw",
        assigned_to_mission="ICU Tent Power",
        target_node_id="node-B",
    )

    state = node_b.get_state()["scarce_item"]["gen-50kw"]
    assert state["token_holder"] == "node-B"
    assert state["status"] == "CONFIRMED_ALLOCATED"

    # Mission completes: Node B releases generator back to AVAILABLE
    TokenManager.release_item(node_b, "gen-50kw", notes="Grid power restored to ICU")
    state_after = node_b.get_state()["scarce_item"]["gen-50kw"]
    assert state_after["status"] == "AVAILABLE"
    assert state_after["allocated_to"] is None

    node_a.close()
    node_b.close()


def test_human_in_the_loop_conflict_resolution():
    """
    Requirement 2: Zero lost updates for conflicting person reports,
    followed by human triage resolution.
    """
    transport = InMemoryTransport()
    node_a = Node("node-A", ":memory:", transport)
    node_b = Node("node-B", ":memory:", transport)

    # Both nodes register differing reports offline
    node_a.record_event("person", "p-maria", "CREATE", {
        "name": "Maria Santos", "status": "MISSING", "location": "Bridge 14"
    })
    node_b.record_event("person", "p-maria", "UPDATE", {
        "status": "INJURED_AT_CLINIC", "location": "Field Hospital B"
    })

    node_a.sync_with("node-B")

    person = node_a.get_state()["person"]["p-maria"]
    assert len(person["conflicts"]) == 1
    assert person["conflicts"][0]["conflicting_status"] == "INJURED_AT_CLINIC"

    # Volunteer at Node A verifies Maria in person and submits formal conflict resolution
    ConflictResolver.resolve_person_conflict(
        node=node_a,
        person_id="p-maria",
        verified_status="FOUND_SAFE_RECOVERING",
        verified_location="Field Hospital B (Bed 12)",
        resolution_notes="Physician verified identity with national ID card",
    )

    node_a.sync_with("node-B")

    resolved_person = node_b.get_state()["person"]["p-maria"]
    assert resolved_person["status"] == "FOUND_SAFE_RECOVERING"
    assert resolved_person["location"] == "Field Hospital B (Bed 12)"
    assert len(resolved_person["conflicts"]) == 0  # Cleared from active dispute
    assert len(resolved_person["archived_conflicts"]) == 1  # Audit trail fully preserved!

    node_a.close()
    node_b.close()
