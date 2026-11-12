"""
UI Controller Logic for RescueNet Streamlit Demo.
Decouples state transitions (cut network, heal network, sync mesh, conflict injection)
from Streamlit rendering so the workflow can be thoroughly unit-tested.
"""

from __future__ import annotations
from typing import List, Dict, Any
from simulator.engine import DisasterSimulator


def create_ui_simulator() -> DisasterSimulator:
    """Create and bootstrap the 3-node disaster coordination simulator for the UI."""
    sim = DisasterSimulator(["alpha-harbor", "beta-hospital", "gamma-mountain"], seed=42)
    sim.bootstrap_default_scenario()
    return sim


def cut_network_partition(sim: DisasterSimulator) -> List[List[str]]:
    """Simulate a hurricane split separating gamma-mountain from alpha/beta."""
    groups = [["alpha-harbor", "beta-hospital"], ["gamma-mountain"]]
    sim.partition_manager.set_partitions(groups)
    return groups


def heal_network_links(sim: DisasterSimulator) -> None:
    """Restore all radio links across the 3-node mesh."""
    sim.partition_manager.heal_all()


def run_mesh_sync(sim: DisasterSimulator) -> List[str]:
    """Execute pairwise anti-entropy sync across connected links and return log lines."""
    sync_results = []
    node_ids = sim.node_ids
    for i in range(len(node_ids)):
        for j in range(i + 1, len(node_ids)):
            n1, n2 = node_ids[i], node_ids[j]
            stats = sim.nodes[n1].sync_with(n2)
            if stats.success:
                sync_results.append(
                    f"OK {n1} <-> {n2}: {stats.events_sent + stats.events_received} ev, {stats.total_bytes} B"
                )
            else:
                sync_results.append(f"CUT {n1} <-> {n2}: Partition Cut")
    return sync_results


def inject_conflicting_doctor_sightings(sim: DisasterSimulator) -> None:
    """Inject concurrent conflicting reports for Dr. Stone on Alpha and Gamma."""
    sim.nodes["alpha-harbor"].record_event(
        entity_type="person",
        entity_id="person-dr-stone",
        operation="UPDATE",
        payload={"name": "Dr. Elizabeth Stone", "status": "MISSING", "location": "Collapsed Bridge 14"},
    )
    sim.nodes["gamma-mountain"].record_event(
        entity_type="person",
        entity_id="person-dr-stone",
        operation="UPDATE",
        payload={"name": "Dr. Elizabeth Stone", "status": "FOUND_SAFE", "location": "Highland Mountain Shelter"},
    )


def check_mesh_convergence(sim: DisasterSimulator) -> bool:
    """Check whether all 3 nodes have identical version vectors and projected state."""
    first_node_id = sim.node_ids[0]
    first_state = sim.nodes[first_node_id].get_state()
    first_vv = sim.nodes[first_node_id].get_version_vector()

    for nid in sim.node_ids[1:]:
        if sim.nodes[nid].get_version_vector() != first_vv or sim.nodes[nid].get_state() != first_state:
            return False
    return True
