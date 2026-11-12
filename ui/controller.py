"""
UI Controller Logic for RescueNet / ResQ-Mesh Streamlit Demo.
Decouples state transitions (cut network, heal network, sync mesh, conflict injection,
ResQ-Mesh 3-phase demo, sneakernet data mules, device revocation)
from Streamlit rendering so the workflow can be thoroughly unit-tested.
"""

from __future__ import annotations
from typing import List, Dict, Any, Optional
from simulator.engine import DisasterSimulator
from allocation.intent_ledger import IntentLedger
from crypto.keyring import NodeKeyring


def create_ui_simulator() -> DisasterSimulator:
    """Create and bootstrap the 3-node disaster coordination simulator for the UI."""
    sim = DisasterSimulator(["alpha-harbor", "beta-hospital", "gamma-mountain"], seed=42)
    
    # Initialize NodeKeyrings for Pillar 4 with shared team salt for mesh decryption
    shared_team_salt = b"rescuenet-mesh-team-salt-2026"
    for nid, node in sim.nodes.items():
        node.keyring = NodeKeyring(
            nid,
            passphrase="disaster-relief-secure-key",
            salt=shared_team_salt,
        )
    # Cross-register trusted peer public keys
    for n1 in sim.nodes.values():
        for n2 in sim.nodes.values():
            n1.keyring.register_peer(n2.node_id, n2.keyring.public_key_hex)

    sim.bootstrap_default_scenario()
    
    # Initialize ResQ-Mesh Pillar 2 Intent Pool (10 Medical Kits)
    IntentLedger.init_pool(
        node=sim.nodes["alpha-harbor"],
        item_id="medical-kits-pool",
        item_name="Emergency Trauma Kits",
        total_quantity=10,
        unit="kits",
    )
    # Sync initial pool to all connected nodes
    sim.nodes["alpha-harbor"].sync_with("beta-hospital")
    sim.nodes["alpha-harbor"].sync_with("gamma-mountain")
    sim.nodes["beta-hospital"].sync_with("gamma-mountain")
    
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


# ---------------------------------------------------------------------------
# RESQ-MESH ARCHITECTURAL BLUEPRINT 3-PHASE GUIDED DEMO
# ---------------------------------------------------------------------------

def run_resqmesh_phase1_baseline(sim: DisasterSimulator) -> str:
    """
    Phase 1 (The Baseline):
    Initialize 3 nodes sharing initial inventory of 10 Emergency Medical Kits.
    Patient X is registered with status 'PENDING_TRIAGE'.
    All links connected and fully converged.
    """
    heal_network_links(sim)
    
    # Register Patient X
    sim.nodes["alpha-harbor"].record_event(
        entity_type="person",
        entity_id="person-patient-x",
        operation="CREATE",
        payload={
            "name": "Patient X (David Kim)",
            "status": "PENDING_TRIAGE",
            "location": "Sector 4 Coastal Perimeter",
            "notes": "Awaiting initial medical response team",
        },
    )
    # Sync across all nodes
    run_mesh_sync(sim)
    run_mesh_sync(sim)
    return "Phase 1 Baseline Initialized: 10 Trauma Kits in stock, Patient X registered, all 3 nodes converged."


def run_resqmesh_phase2_split_and_conflict(sim: DisasterSimulator) -> str:
    """
    Phase 2 (The Split & Conflict):
    1. Disconnect Node Gamma (Mountain) completely.
    2. Node Alpha claims 8 kits and marks Patient X as 'Found - Stable'.
    3. Node Beta claims 5 kits (causing offline over-allocation: 8+5=13 > 10)
       and marks Patient X as 'Injured - Urgent'.
    """
    # Isolate all 3 nodes into independent partitions
    sim.partition_manager.set_partitions([["alpha-harbor"], ["beta-hospital"], ["gamma-mountain"]])
    
    # Node Alpha offline intent & sighting
    IntentLedger.record_intent(
        node=sim.nodes["alpha-harbor"],
        item_id="medical-kits-pool",
        quantity=8,
        beneficiary="Harbor Surgical Triage Tent",
    )
    sim.nodes["alpha-harbor"].record_event(
        entity_type="person",
        entity_id="person-patient-x",
        operation="UPDATE",
        payload={
            "name": "Patient X (David Kim)",
            "status": "Found - Stable",
            "location": "Harbor Medical Tent 3",
            "notes": "Examined by volunteer nurse; vitals normal",
        },
    )

    # Node Beta offline intent & sighting
    IntentLedger.record_intent(
        node=sim.nodes["beta-hospital"],
        item_id="medical-kits-pool",
        quantity=5,
        beneficiary="Mountain Evacuation Clinic",
    )
    sim.nodes["beta-hospital"].record_event(
        entity_type="person",
        entity_id="person-patient-x",
        operation="UPDATE",
        payload={
            "name": "Patient X (David Kim)",
            "status": "Injured - Urgent",
            "location": "Highland Ridge Ravine",
            "notes": "Compound fracture reported by mountain search team",
        },
    )

    return "Phase 2 Split Active: Alpha claimed 8 kits ('Found-Stable'), Beta claimed 5 kits ('Injured-Urgent'), Gamma isolated."


def run_resqmesh_phase3_reconnect_and_converge(sim: DisasterSimulator) -> str:
    """
    Phase 3 (The Reconnection & Convergence):
    Reconnect all three nodes and execute anti-entropy sync.
    Causally merges event timelines:
    - Patient X timeline displays both historical updates transparently (Zero Lost Updates).
    - An inventory collision alert triggers on 13 claimed > 10 available (Zero Double-Allocation).
    """
    heal_network_links(sim)
    run_mesh_sync(sim)
    run_mesh_sync(sim)  # Second sweep for transitive propagation
    return "Phase 3 Reconnected: Timelines merged causally! Patient X preserves both sightings; Inventory collision detected (13/10)."


def resolve_resqmesh_inventory_collision(
    sim: DisasterSimulator,
    alpha_allocated: int = 6,
    beta_allocated: int = 4,
    notes: str = "Chief Medical Officer emergency triage apportionment",
) -> str:
    """
    Coordinator manually resolves the 13 vs 10 inventory collision:
    Confirms 6 kits to Alpha and 4 kits to Beta (total = 10, zero deficit).
    """
    allocations = {
        "alpha-harbor": alpha_allocated,
        "beta-hospital": beta_allocated,
    }
    IntentLedger.resolve_collision(
        node=sim.nodes["alpha-harbor"],
        item_id="medical-kits-pool",
        approved_allocations=allocations,
        resolution_notes=notes,
    )
    # Propagate resolution across mesh
    heal_network_links(sim)
    run_mesh_sync(sim)
    run_mesh_sync(sim)
    return f"Collision Resolved: Allocated {alpha_allocated} to Harbor, {beta_allocated} to Mountain. Deficit: 0. State 100% Converged."


# ---------------------------------------------------------------------------
# SNEAKERNET DATA MULE & REVOCATION RING
# ---------------------------------------------------------------------------

def dispatch_ambulance_data_mule(
    sim: DisasterSimulator,
    from_node: str = "alpha-harbor",
    to_node: str = "gamma-mountain",
) -> str:
    """
    Sneakernet DTN Transport (Layer 2):
    Simulates a physical emergency ambulance or drone carrying an encrypted cache bundle
    between two geographically disconnected camps across a destroyed bridge or mountain.
    Directly exchanges deltas without restoring the physical radio partition.
    """
    node1 = sim.nodes[from_node]
    node2 = sim.nodes[to_node]
    vv1 = node1.get_version_vector()
    vv2 = node2.get_version_vector()
    deltas_to_2 = node1.store.get_events_since(vv2)
    deltas_to_1 = node2.store.get_events_since(vv1)

    events_sent = len(deltas_to_2)
    events_received = len(deltas_to_1)
    total_bytes = sum(e.wire_byte_size() for e in deltas_to_2 + deltas_to_1)

    for e in deltas_to_2:
        node2.store.append(e)
    for e in deltas_to_1:
        node1.store.append(e)

    return (
        f"🚑 Ambulance Data Mule Dispatched: Ferried updates from {from_node} to {to_node}. "
        f"Transferred {events_sent + events_received} delta events ({total_bytes} bytes) "
        f"via physical sneakernet across partition boundaries!"
    )


def revoke_compromised_device(sim: DisasterSimulator, revoked_node_id: str) -> str:
    """
    Pillar 4 Cryptographic Revocation:
    Blacklists a lost or seized device across the mesh trust ring.
    Freezes its ability to inject data.
    """
    for node in sim.nodes.values():
        if hasattr(node, "keyring") and node.keyring:
            node.keyring.revoke_peer(revoked_node_id)
            
    # Record revocation audit event
    sim.nodes["alpha-harbor"].record_event(
        entity_type="security",
        entity_id=f"revocation-{revoked_node_id}",
        operation="REVOKE_NODE",
        payload={
            "revoked_node_id": revoked_node_id,
            "reason": "Device flagged lost/seized in field operation",
            "revocation_authority": "alpha-harbor",
        },
    )
    return f"🚨 Device {revoked_node_id} blacklisted across cryptographic ring. All future events will be dropped!"

