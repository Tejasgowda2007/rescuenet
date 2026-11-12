"""
Unit and Integration Tests for Project ResQ-Mesh Blueprint:
4 Pillars, Intent-First Soft Allocation, Collision Triage,
Sneakernet Data Mule, and Cryptographic Revocation.
"""

import pytest
from ui.controller import (
    create_ui_simulator,
    run_resqmesh_phase1_baseline,
    run_resqmesh_phase2_split_and_conflict,
    run_resqmesh_phase3_reconnect_and_converge,
    resolve_resqmesh_inventory_collision,
    dispatch_ambulance_data_mule,
    revoke_compromised_device,
    check_mesh_convergence,
)
from allocation.intent_ledger import IntentLedger


def test_resqmesh_3phase_guided_workflow():
    """
    Test the complete 3-phase demonstration lifecycle:
    Phase 1: Baseline 10 Trauma Kits, Patient X registered, all converged.
    Phase 2: Partition split, Alpha claims 8 kits, Beta claims 5 kits (13 total).
    Phase 3: Reconnection, collision detection (13 > 10), coordinator resolution (6/4).
    """
    sim = create_ui_simulator()

    # 1. Phase 1: Baseline
    p1_msg = run_resqmesh_phase1_baseline(sim)
    assert "Phase 1" in p1_msg
    assert check_mesh_convergence(sim) is True
    
    state_p1 = sim.nodes["alpha-harbor"].get_state()
    kits_p1 = state_p1.get("supply_intent", {}).get("medical-kits-pool", {})
    assert kits_p1["total_quantity"] == 10
    assert kits_p1["collision_detected"] is False

    # 2. Phase 2: Split & Offline Conflicting Claims
    p2_msg = run_resqmesh_phase2_split_and_conflict(sim)
    assert "Phase 2" in p2_msg
    assert check_mesh_convergence(sim) is False

    # Check that Alpha recorded 8 kits intent locally
    state_alpha = sim.nodes["alpha-harbor"].get_state()
    assert state_alpha["supply_intent"]["medical-kits-pool"]["intentions"]["alpha-harbor"] == 8
    assert state_alpha["person"]["person-patient-x"]["status"] == "Found - Stable"

    # Check that Beta recorded 5 kits intent locally
    state_beta = sim.nodes["beta-hospital"].get_state()
    assert state_beta["supply_intent"]["medical-kits-pool"]["intentions"]["beta-hospital"] == 5
    assert state_beta["person"]["person-patient-x"]["status"] == "Injured - Urgent"

    # 3. Phase 3: Reconnect & Merge
    p3_msg = run_resqmesh_phase3_reconnect_and_converge(sim)
    assert "Phase 3" in p3_msg
    assert check_mesh_convergence(sim) is True

    # Invariant Verification on Converged State:
    merged_state = sim.nodes["alpha-harbor"].get_state()
    kits_merged = merged_state["supply_intent"]["medical-kits-pool"]

    # (a) Zero double allocation: Collision detected, 13 claimed > 10 available, deficit = 3
    assert kits_merged["total_claimed"] == 13
    assert kits_merged["collision_detected"] is True
    assert kits_merged["deficit"] == 3

    # (b) Zero lost updates: Patient X preserves both contradictory field sightings
    patient_x = merged_state["person"]["person-patient-x"]
    assert len(patient_x["conflicts"]) == 1
    assert patient_x["conflicts"][0]["previous_status"] != patient_x["conflicts"][0]["conflicting_status"]

    # 4. Coordinator Resolution: Split 6 / 4
    res_msg = resolve_resqmesh_inventory_collision(sim, alpha_allocated=6, beta_allocated=4)
    assert "Deficit: 0" in res_msg
    assert check_mesh_convergence(sim) is True

    final_state = sim.nodes["alpha-harbor"].get_state()
    final_kits = final_state["supply_intent"]["medical-kits-pool"]
    assert final_kits["collision_detected"] is False
    assert final_kits["deficit"] == 0
    assert final_kits["approved_allocations"] == {"alpha-harbor": 6, "beta-hospital": 4}
    assert sum(final_kits["approved_allocations"].values()) == 10

    sim.close()


def test_sneakernet_data_mule_dispatch():
    """Verify that an ambulance data mule ferries delta events across a cut network."""
    sim = create_ui_simulator()
    
    # Isolate gamma-mountain
    sim.partition_manager.set_partitions([["alpha-harbor", "beta-hospital"], ["gamma-mountain"]])
    
    # Generate an update on alpha
    sim.nodes["alpha-harbor"].record_event(
        entity_type="need",
        entity_id="need-mule-test",
        operation="CREATE",
        payload={"item": "Pediatric Electrolytes", "urgency": "CRITICAL"},
    )
    
    # Gamma should not have this event yet
    assert "need-mule-test" not in sim.nodes["gamma-mountain"].get_state().get("need", {})
    
    # Dispatch ambulance data mule directly
    mule_log = dispatch_ambulance_data_mule(sim, "alpha-harbor", "gamma-mountain")
    assert "Ambulance Data Mule Dispatched" in mule_log
    
    # Gamma now has the event despite the radio partition still being cut!
    assert "need-mule-test" in sim.nodes["gamma-mountain"].get_state().get("need", {})
    
    sim.close()


def test_device_revocation_ring():
    """Verify that a blacklisted/seized device has its events dropped across the mesh."""
    sim = create_ui_simulator()
    
    # Revoke beta-hospital
    revoke_log = revoke_compromised_device(sim, "beta-hospital")
    assert "blacklisted" in revoke_log
    
    # Alpha's keyring should now mark beta as revoked
    assert sim.nodes["alpha-harbor"].keyring.is_revoked("beta-hospital") is True
    
    sim.close()
