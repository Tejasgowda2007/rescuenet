"""
Unit and Integration Tests for Stage 8: Streamlit UI Controller and App Syntax.
"""

import os
import py_compile
import pytest
from ui.controller import (
    create_ui_simulator,
    cut_network_partition,
    heal_network_links,
    run_mesh_sync,
    inject_conflicting_doctor_sightings,
    check_mesh_convergence,
)


def test_ui_app_compiles_cleanly():
    """Verify ui/app.py has valid Python syntax with zero compile errors."""
    app_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "ui", "app.py"))
    py_compile.compile(app_path, doraise=True)


def test_ui_controller_cut_heal_conflict_convergence_workflow():
    """
    Simulate the exact user workflow triggered by the Streamlit UI buttons:
    1. Boot 3 nodes (Alpha, Beta, Gamma) -> converged initially.
    2. Cut Network -> mountain shelter isolated.
    3. Inject conflicting doctor sightings -> nodes diverge.
    4. Sync Mesh while partitioned -> Alpha & Beta sync, Gamma remains blocked.
    5. Heal Network & Sync Mesh -> all 3 nodes converge 100%, conflict ledger preserved.
    """
    sim = create_ui_simulator()
    assert check_mesh_convergence(sim) is True

    # 1. Cut Network
    groups = cut_network_partition(sim)
    assert len(sim.partition_manager.get_connected_components()) == 2
    assert groups == [["alpha-harbor", "beta-hospital"], ["gamma-mountain"]]

    # 2. Inject conflicting sightings
    inject_conflicting_doctor_sightings(sim)
    assert check_mesh_convergence(sim) is False

    # 3. Sync while partitioned
    logs_cut = run_mesh_sync(sim)
    assert any("Partition Cut" in log for log in logs_cut)
    assert check_mesh_convergence(sim) is False

    # 4. Heal Network & Sync Mesh
    heal_network_links(sim)
    assert len(sim.partition_manager.get_connected_components()) == 1

    logs_healed = run_mesh_sync(sim)
    # Transitive sweep
    run_mesh_sync(sim)
    assert all("OK" in log for log in logs_healed)
    assert check_mesh_convergence(sim) is True

    # 5. Verify zero lost updates (conflict preserved)
    state = sim.nodes["alpha-harbor"].get_state()
    dr_stone = state["person"]["person-dr-stone"]
    assert len(dr_stone["conflicts"]) == 1

    sim.close()
