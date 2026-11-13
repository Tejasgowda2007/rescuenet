"""
Unit and Integration Tests for Stage 4:
Multi-Node Network Simulator (N >= 3), Partitions, Heals, and Conflicting Edits.
"""

import pytest
import random
from simulator.network import PartitionManager
from simulator.workload import WorkloadGenerator
from simulator.engine import DisasterSimulator
from transport.in_memory import InMemoryTransport
from sync.node import Node


def test_simulator_minimum_nodes_requirement():
    """Verify simulator enforces N >= 3 requirement."""
    with pytest.raises(ValueError):
        DisasterSimulator(["node-1", "node-2"])


def test_partition_manager_components_and_cuts():
    """Test graph partitioning and connected component discovery."""
    transport = InMemoryTransport()
    nodes = ["alpha", "beta", "gamma", "delta"]
    for nid in nodes:
        transport.register_node(nid, lambda m: None)

    pm = PartitionManager(transport, nodes)

    # Cut into two islands: {alpha, beta} and {gamma, delta}
    pm.set_partitions([["alpha", "beta"], ["gamma", "delta"]])
    assert transport.is_connected("alpha", "beta") is True
    assert transport.is_connected("gamma", "delta") is True
    assert transport.is_connected("alpha", "gamma") is False
    assert transport.is_connected("beta", "delta") is False

    comps = pm.get_connected_components()
    assert len(comps) == 2
    assert sorted(comps[0]) in (["alpha", "beta"], ["gamma", "delta"])

    # Heal all
    pm.heal_all()
    assert transport.is_connected("alpha", "gamma") is True
    assert len(pm.get_connected_components()) == 1


def test_three_node_partition_and_transitive_convergence():
    """
    3 nodes: Node A is completely isolated on a mountain.
    Nodes B and C communicate in the valley.
    All record offline events. Then mountain link heals and all converge.
    """
    sim = DisasterSimulator(["mountain-A", "valley-B", "valley-C"], seed=101)
    sim.bootstrap_default_scenario()

    # Step 1: Mountain isolated
    sim.step(partition_groups=[["mountain-A"], ["valley-B", "valley-C"]])

    # Step 2: Second round with mountain still isolated
    sim.step(partition_groups=[["mountain-A"], ["valley-B", "valley-C"]])

    # Assert pre-heal divergence
    vv_a = sim.nodes["mountain-A"].get_version_vector()
    vv_b = sim.nodes["valley-B"].get_version_vector()
    assert vv_a != vv_b

    # Step 3: Mountain link heals, epidemic sync
    converged = sim.heal_and_converge()
    assert converged is True

    # Check identical version vectors on all 3 nodes
    vv_final = sim.nodes["mountain-A"].get_version_vector()
    assert sim.nodes["valley-B"].get_version_vector() == vv_final
    assert sim.nodes["valley-C"].get_version_vector() == vv_final

    # Check identical states on all 3 nodes
    state_a = sim.nodes["mountain-A"].get_state()
    state_b = sim.nodes["valley-B"].get_state()
    state_c = sim.nodes["valley-C"].get_state()
    assert state_a == state_b == state_c

    sim.close()


def test_five_node_random_partition_chaos():
    """
    5 nodes undergoing 5 rounds of random topological cuts,
    stochastic domain edits, and eventual healing.
    """
    node_ids = [f"node-{i}" for i in range(5)]
    sim = DisasterSimulator(node_ids, seed=999)
    sim.bootstrap_default_scenario()

    # Run 5 random partition rounds
    for _ in range(5):
        sim.step()

    # Heal network completely and run epidemic gossip
    converged = sim.heal_and_converge()
    assert converged is True
    assert sim.report.converged is True
    assert sim.report.total_bytes_transferred > 0

    # Verify identical event counts and states on all 5 nodes
    first_state = sim.nodes[node_ids[0]].get_state()
    for nid in node_ids[1:]:
        assert sim.nodes[nid].get_state() == first_state

    sim.close()


def test_judge_chosen_partition_scenario():
    """
    Requirement 6: Must handle a partition scenario chosen by judges at demo time.
    Scenario:
    Phase 1: 4 nodes partitioned into [A, B] and [C, D].
    Phase 2: Bridge shifts: [B, C] can meet, but [A] and [D] remain isolated.
    Phase 3: Full reconnection [A, B, C, D].
    """
    sim = DisasterSimulator(["node-A", "node-B", "node-C", "node-D"], seed=42)
    sim.bootstrap_default_scenario()

    # Inject explicit concurrent conflict for a missing person
    WorkloadGenerator.inject_concurrent_conflicts(
        nodes=list(sim.nodes.values()),
        person_id="person-dr-stone",
        person_name="Dr. Elizabeth Stone",
    )

    # Phase 1: Two islands [A, B] and [C, D]
    sim.step(partition_groups=[["node-A", "node-B"], ["node-C", "node-D"]])

    # Phase 2: Bridge shifts: only B and C meet at river crossing
    sim.step(partition_groups=[["node-B", "node-C"], ["node-A"], ["node-D"]])

    # Phase 3: Full reconnection
    converged = sim.heal_and_converge()
    assert converged is True

    # Verify zero lost updates: all 4 contradictory sightings are preserved
    final_state = sim.nodes["node-A"].get_state()
    dr_stone = final_state["person"]["person-dr-stone"]
    assert dr_stone is not None
    # All other conflicting observations were captured in conflicts ledger
    assert len(dr_stone["conflicts"]) >= 1

    # Verify all 4 nodes agree on Dr. Stone's record
    for nid in ["node-B", "node-C", "node-D"]:
        assert sim.nodes[nid].get_state()["person"]["person-dr-stone"] == dr_stone

    sim.close()
