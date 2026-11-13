"""
Unit and Integration Tests for Stage 8: Streamlit UI Controller and App Syntax.
"""

import json
import os
import py_compile
import pytest
from ui.controller import (
    create_ui_simulator,
    cut_network_partition,
    set_custom_partition,
    toggle_link,
    heal_network_links,
    run_mesh_sync,
    inject_conflicting_doctor_sightings,
    run_scenario_preset,
    check_mesh_convergence,
    export_node_bundle_json,
    import_node_bundle_json,
    get_node_timeline,
    build_mesh_topology_svg,
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


def test_ui_crypto_timeline_svg_and_link_toggles():
    """Verify crypto-enabled UI simulator, timeline inspection, link toggles, and SVG output."""
    sim = create_ui_simulator(enable_crypto=True)
    assert check_mesh_convergence(sim) is True

    # Log PII event and inspect raw ciphertext vs decrypted timeline
    sim.nodes["alpha-harbor"].record_event(
        "person", "person-test", "UPDATE", {"name": "Elena Rostova", "status": "FOUND_SAFE", "location": "Dock 2"}
    )
    timeline = get_node_timeline(sim, "alpha-harbor", limit=5)
    latest = timeline[0]
    assert latest["signed"] is True
    assert latest["sig_valid"] is True
    assert latest["encrypted_pii"] is True
    assert latest["payload"]["name"] == "Elena Rostova"
    assert latest["raw_payload"]["name"]["__enc__"] is True

    # Toggle direct link alpha <-> gamma off and check SVG reflects both states
    assert toggle_link(sim, "alpha-harbor", "gamma-mountain") is False
    svg = build_mesh_topology_svg(sim)
    assert "<svg" in svg
    assert "LINK CUT" in svg
    assert "LINK UP" in svg
    assert "BOAT TOKEN" in svg

    # 2-hop relay sync through beta should still converge alpha <-> beta <-> gamma
    run_mesh_sync(sim)
    run_mesh_sync(sim)
    assert check_mesh_convergence(sim) is True

    sim.close()


def test_ui_presets_and_usb_sneakernet_bundle_sync():
    """Verify scenario presets and offline USB JSON bundle export/import with tamper rejection."""
    sim = create_ui_simulator(enable_crypto=True)

    # Cut all links completely and run a preset
    logs = run_scenario_preset(sim, "flash_flood")
    assert len(logs) == 1
    assert check_mesh_convergence(sim) is False

    # Isolate all 3 nodes so zero radio sync is possible
    comps = set_custom_partition(sim, "split_all")
    assert len(comps) == 3

    # Export Alpha -> Import into Gamma via USB sneakernet bundle
    bundle_alpha = export_node_bundle_json(sim, "alpha-harbor")
    res = import_node_bundle_json(sim, "gamma-mountain", bundle_alpha)
    assert res["applied"] > 0
    assert res["rejected"] == 0

    # Tampered event inside USB bundle must be rejected by signature check
    tampered = json.loads(bundle_alpha)
    tampered["events"][-1]["payload"]["tampered"] = "evil"
    tampered_res = import_node_bundle_json(sim, "beta-hospital", json.dumps(tampered))
    assert tampered_res["rejected"] >= 1

    # Chain relay & supply crunch presets execute cleanly
    sim2 = create_ui_simulator(enable_crypto=True)
    assert len(run_scenario_preset(sim2, "supply_crunch")) == 1
    assert len(run_scenario_preset(sim2, "chain_mule")) == 1

    sim.close()
    sim2.close()
