"""
Unit and Integration Tests for Stage 5:
Automatic Proof Harness Invariant Verification, Adversarial Rejection, and Partition Link Integrity.
"""

import os
import pytest
from simulator.proof_harness import ProofHarness, ProofReport
from simulator.engine import DisasterSimulator
from transport.in_memory import InMemoryTransport
from sync.node import Node
from allocation.escrow import EscrowManager
from allocation.tokens import TokenManager
from events.event import Event


def test_proof_harness_single_scenario_all_invariants():
    """Verify that a single randomized trial strictly satisfies all 4 invariants."""
    harness = ProofHarness(base_seed=42)
    res = harness.run_scenario(scenario_id=1, num_nodes=4, num_rounds=3, actions_per_node_per_round=3)

    assert res.passed is True
    assert res.state_converged is True
    assert res.zero_lost_updates is True
    assert res.no_double_allocations is True
    assert res.escrow_conserved is True
    assert res.total_bytes > 0
    assert res.events_generated > 0


def test_proof_harness_batch_50_scenarios():
    """
    Run 50 randomized trials across variable node counts (3 to 5 nodes)
    with multiple actions per round and verify 100% pass rate.
    """
    harness = ProofHarness(base_seed=999)
    report = harness.run_proof_suite(num_scenarios=50)

    assert report.total_scenarios == 50
    assert report.passed_scenarios == 50
    assert report.failed_scenarios == 0
    assert report.pass_rate() == 100.0
    assert report.state_convergence_passes == 50
    assert report.zero_lost_updates_passes == 50
    assert report.no_double_allocation_passes == 50
    assert report.escrow_conservation_passes == 50


def test_scorecard_formatting_and_dynamic_verdict():
    """
    Requirement 1: Verify VERDICT column is computed dynamically from real pass counts
    and 'FORMAL' is removed from the final line.
    """
    harness = ProofHarness(base_seed=123)
    report = harness.run_proof_suite(num_scenarios=5)
    scorecard = harness.format_scorecard_table(report)

    assert "SCORECARD" in scorecard
    assert "Identical State Convergence" in scorecard
    assert "Zero Lost Updates" in scorecard
    assert "Indivisible Item Double Alloc=0" in scorecard
    assert "Divisible Supply Escrow Balance" in scorecard
    assert "| PASS" in scorecard
    # Verify 'FORMAL' is removed from final line
    assert "FORMAL" not in scorecard.splitlines()[-2]
    assert "CONVERGENCE" in scorecard.splitlines()[-2]


def test_misbehaving_node_direct_over_allocation_rejected():
    """
    Requirement 4: Test with a misbehaving/rogue node that writes an over-allocating
    event directly to SQLite, bypassing validation.
    Verifies that:
    1. Peers ingest the event but the StateProjector rejects the over-allocation.
    2. Invariant (d) recomputed from raw events refuses to count over-allocations.
    3. An unauthorized scarce item allocation attempt is flagged and ignored.
    """
    transport = InMemoryTransport()
    honest_node = Node("honest-node", ":memory:", transport)
    rogue_node = Node("rogue-node", ":memory:", transport)

    # Depot creates pool of 100 medical supplies (50 honest, 50 rogue)
    EscrowManager.create_pool(
        node=honest_node,
        supply_id="supply-insulin",
        item_name="Insulin 100IU",
        total_quantity=100,
        initial_quotas={"honest-node": 50, "rogue-node": 50},
    )
    # Honest node registers boat; honest-node holds the token
    TokenManager.register_item(
        node=honest_node,
        item_id="boat-alpha",
        item_name="Rescue Boat Alpha",
        initial_holder_id="honest-node",
    )
    honest_node.sync_with("rogue-node")

    # Honest node consumes 10 within quota
    EscrowManager.consume(honest_node, "supply-insulin", 10, "Clinic Sector 1")

    # Rogue node deliberately BYPASSES EscrowManager and directly appends a fraudulent over-allocation
    # Rogue has quota 50, but writes an event consuming 9,999 units directly into its SQLite store!
    rogue_fraud_event = Event(
        node_id="rogue-node",
        counter=rogue_node._local_counter + 1,
        timestamp=1000.0,
        entity_type="supply",
        entity_id="supply-insulin",
        operation="CONSUME_QUOTA",
        payload={"quantity": 9999, "beneficiary": "Black Market"},
    )
    rogue_node.store.append(rogue_fraud_event)

    # Rogue node also writes an unauthorized CONFIRM_ALLOCATION for the boat (does NOT hold token!)
    rogue_boat_event = Event(
        node_id="rogue-node",
        counter=rogue_node._local_counter + 2,
        timestamp=1005.0,
        entity_type="scarce_item",
        entity_id="boat-alpha",
        operation="CONFIRM_ALLOCATION",
        payload={"assigned_to": "Rogue Command Base", "target_node": "rogue-node"},
    )
    rogue_node.store.append(rogue_boat_event)

    # Honest node syncs with rogue node
    honest_node.sync_with("rogue-node")

    # 1. Verify honest node's projected state REJECTED the fraudulent supply over-allocation
    state = honest_node.get_state()
    insulin_data = state["supply"]["supply-insulin"]
    assert insulin_data["consumed"] == 10  # Only honest node's 10 was counted!
    assert insulin_data["quotas"]["rogue-node"] == 50  # Rogue's quota never went negative!
    # Over-allocation logged in rejected_allocations
    assert len(insulin_data["rejected_allocations"]) == 1
    assert insulin_data["rejected_allocations"][0]["attempted_quantity"] == 9999

    # 2. Verify scarce item was NOT allocated to the rogue node
    boat_data = state["scarce_item"]["boat-alpha"]
    assert boat_data["status"] == "AVAILABLE"
    assert boat_data["allocated_to"] is None
    assert len(boat_data["rejected_allocations"]) == 1
    assert boat_data["rejected_allocations"][0]["attempted_by"] == "rogue-node"

    # 3. Verify Conservation Invariant holds:
    assert insulin_data["consumed"] + sum(insulin_data["quotas"].values()) == 100

    honest_node.close()
    rogue_node.close()


def test_random_partition_cuts_transport_links_used_by_sync():
    """
    Requirement 5: Confirm random_partition actually cuts links in the transport
    that sync_with uses.
    """
    node_ids = ["node-A", "node-B", "node-C", "node-D"]
    sim = DisasterSimulator(node_ids=node_ids, seed=42)
    sim.bootstrap_default_scenario()

    # Verify transport instance identity
    assert sim.partition_manager.transport is sim.transport
    for nid, node in sim.nodes.items():
        assert node.transport is sim.transport

    # Force a 2-group random partition: [[n1, n2], [n3, n4]]
    groups = sim.partition_manager.random_partition(sim.rng, min_groups=2, max_groups=2)
    assert len(groups) == 2
    grp0 = groups[0]
    grp1 = groups[1]

    # Verify links across different groups are CUT in the transport
    for u in grp0:
        for v in grp1:
            assert sim.transport.is_connected(u, v) is False, f"Link between {u} and {v} should be cut!"
            # Log event on u
            sim.nodes[u].record_event("need", f"need-cut-{u}", "CREATE", {"desc": "Isolated Need"})
            # Attempt sync across the cut -> MUST fail!
            stats = sim.nodes[u].sync_with(v)
            assert stats.success is False
            assert stats.events_received == 0
            assert "unreachable" in stats.error.lower()

    # Verify links within the same group remain CONNECTED in the transport
    if len(grp0) >= 2:
        u1, u2 = grp0[0], grp0[1]
        assert sim.transport.is_connected(u1, u2) is True, f"Link between {u1} and {u2} should be connected!"
        stats_internal = sim.nodes[u1].sync_with(u2)
        assert stats_internal.success is True

    sim.close()
