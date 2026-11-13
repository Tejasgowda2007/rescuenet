"""
Automated Test Suite for RescueNet FieldMesh Digital Twin.
Validates:
- Procedural terrain generation, deterministic seed, and elevation bounds.
- 3D Line-of-sight ray-marching & mountain ridge obstruction.
- Radio propagation link budgets, knife-edge diffraction, and LoRa airtime.
- NetworkX topology graph, Dijkstra multi-hop route discovery, and partitions.
- Packet fragmentation and reassembly.
- TTL loop prevention.
- SimPy discrete-event packet scheduling.
- Offline SQLite independent event persistence.
- RescueNet sync integration over multi-hop simulated radio mesh.
- Single-owner boat token exclusivity & escrow quota conservation.
- Relay tower structural failure and route recovery.
- Security tamper rejection and forged signature defense.
- All 8 disaster scenario presets.
- 5-Minute Hackathon Demo workflow runner.
"""

import os
import sys
import pytest
import numpy as np

# Ensure project root is on sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from fieldmesh.terrain import TerrainModel
from fieldmesh.radio import (
    RadioPropagationModel,
    LORA_DEFAULT_PROFILE,
    DIRECTIONAL_P2P_PROFILE,
)
from fieldmesh.stations import create_default_rescue_stations
from fieldmesh.topology import TopologyManager
from fieldmesh.packet import (
    Packet,
    PacketFragmentationManager,
    PRIORITY_SOS,
    PRIORITY_SYNC,
)
from fieldmesh.engine import SimulationEngine
from fieldmesh.adapter import (
    FieldMeshRadioTransport,
    create_rescuenet_nodes_for_fieldmesh,
)
from fieldmesh.scenarios import ScenarioEngine, SCENARIOS
from fieldmesh.metrics import MetricsAggregator
from fieldmesh.demo_runner import HackathonDemoRunner
from allocation.escrow import EscrowManager, InsufficientQuotaError
from allocation.tokens import TokenManager, UnauthorizedAllocationError
from allocation.conflict_resolver import ConflictResolver
from crypto.keyring import NodeKeyring


@pytest.fixture
def test_setup(tmp_path):
    """Bootstrap deterministic test environment."""
    terrain = TerrainModel(seed=42)
    stations = create_default_rescue_stations(terrain, data_dir=str(tmp_path))
    topology = TopologyManager(terrain, stations)
    engine = SimulationEngine(terrain, stations, topology, seed=42)
    transport = FieldMeshRadioTransport(topology, engine)
    nodes = create_rescuenet_nodes_for_fieldmesh(stations, transport)
    return {
        "terrain": terrain,
        "stations": stations,
        "topology": topology,
        "engine": engine,
        "transport": transport,
        "nodes": nodes,
        "tmp_path": tmp_path,
    }


def test_terrain_procedural_elevation_and_deterministic_seed():
    """Verify 50x50 km terrain generates within expected elevation bounds deterministically."""
    t1 = TerrainModel(seed=42)
    t2 = TerrainModel(seed=42)

    assert t1.elevation_map.shape == (256, 256)
    assert t1.elevation_map.min() >= 300.0
    assert t1.elevation_map.max() <= 2900.0
    # Determinism: identical heightmap across instances
    assert np.array_equal(t1.elevation_map, t2.elevation_map)

    # Subsampled export for Three.js
    sub = t1.export_subsampled_grid(step=4)
    assert sub["rows"] == 64
    assert sub["cols"] == 64
    assert len(sub["features"]) >= 4


def test_mountain_ridge_line_of_sight_obstruction(test_setup):
    """Verify that Trishul Ridge blocks direct Alpha -> Charlie LOS, but Echo relay has LOS."""
    terrain = test_setup["terrain"]
    stations = test_setup["stations"]

    alpha = stations["alpha"]
    charlie = stations["charlie"]
    echo = stations["echo"]

    # 1. Direct Alpha to Charlie across Trishul Ridge
    los_ac = terrain.check_line_of_sight(
        tx_pos=(alpha.x_km, alpha.y_km),
        rx_pos=(charlie.x_km, charlie.y_km),
        tx_mast_height_m=alpha.antenna_mast_m,
        rx_mast_height_m=charlie.antenna_mast_m,
    )
    # Trishul Ridge must obstruct direct line-of-sight
    assert bool(los_ac.has_los) is False
    assert los_ac.max_obstruction_m > 0.0

    # 2. Alpha to Echo Elevated Relay (Summit at 2,350m)
    los_ae = terrain.check_line_of_sight(
        tx_pos=(alpha.x_km, alpha.y_km),
        rx_pos=(echo.x_km, echo.y_km),
        tx_mast_height_m=alpha.antenna_mast_m,
        rx_mast_height_m=echo.antenna_mast_m,
    )
    assert bool(los_ae.has_los) is True

    # 3. Echo Elevated Relay to Charlie Mountain Shelter
    los_ec = terrain.check_line_of_sight(
        tx_pos=(echo.x_km, echo.y_km),
        rx_pos=(charlie.x_km, charlie.y_km),
        tx_mast_height_m=echo.antenna_mast_m,
        rx_mast_height_m=charlie.antenna_mast_m,
    )
    assert bool(los_ec.has_los) is True


def test_radio_propagation_link_budget_and_diffraction(test_setup):
    """Verify FSPL, knife-edge diffraction attenuation, and LoRa airtime calculations."""
    terrain = test_setup["terrain"]

    # Clear path 5 km
    los_clear = terrain.check_line_of_sight((10.0, 10.0), (10.0, 15.0), tx_mast_height_m=20.0, rx_mast_height_m=20.0)
    assessment = RadioPropagationModel.evaluate_link(los_clear, LORA_DEFAULT_PROFILE)

    assert assessment.distance_3d_km > 4.5
    assert assessment.free_space_loss_db > 95.0
    assert assessment.link_status in ("ACTIVE", "DEGRADED")
    assert assessment.one_way_latency_ms > 0.0

    # LoRa airtime for 100 bytes at SF9
    airtime = RadioPropagationModel.calculate_lora_airtime(100, LORA_DEFAULT_PROFILE)
    assert 100.0 < airtime < 800.0  # Typical LoRa SF9 125kHz airtime ~250-600ms


def test_networkx_topology_multi_hop_route_discovery(test_setup):
    """Verify that direct Alpha -> Charlie is blocked, but route discovers Alpha -> Echo -> Charlie."""
    topo = test_setup["topology"]

    # Direct Alpha to Charlie link should not be active
    assert not topo.is_link_connected("alpha", "charlie")

    # Multi-hop Dijkstra path must discover relay through Echo or Delta
    route = topo.get_route("alpha", "charlie")
    assert route is not None
    assert route[0] == "alpha"
    assert route[-1] == "charlie"
    assert len(route) >= 3
    assert ("echo" in route or "delta" in route)


def test_packet_fragmentation_and_reassembly():
    """Verify that payloads exceeding MTU are cleanly fragmented and reassembled in order."""
    frag_mgr = PacketFragmentationManager(mtu_bytes=100)

    large_payload = {
        "event_id": "ev-test-12345",
        "type": "person",
        "description": "Long disaster triage observation notes exceeding single radio frame boundary.",
        "attributes": {"field_a": 1234, "field_b": "extended information payload"},
    }

    packets = frag_mgr.fragment_message(
        source_id="alpha",
        destination_id="charlie",
        msg_type="EVENT_DELTA",
        full_payload=large_payload,
    )
    assert len(packets) > 1

    # Ingest fragments
    reassembled = None
    for pkt in packets:
        result = frag_mgr.receive_fragment(pkt)
        if result is not None:
            reassembled = result

    assert reassembled is not None
    assert reassembled["event_id"] == "ev-test-12345"
    assert reassembled["attributes"]["field_a"] == 1234


def test_ttl_and_loop_prevention():
    """Verify packet TTL decrement and loop avoidance."""
    pkt = Packet(
        packet_id="pkt-loop-test",
        source_id="alpha",
        destination_id="charlie",
        prev_hop="alpha",
        next_hop="echo",
        msg_type="SOS",
        priority=PRIORITY_SOS,
        payload={"msg": "SOS"},
        ttl=2,
    )

    p1 = pkt.create_forward_copy("echo", "charlie")
    assert p1 is not None
    assert p1.ttl == 1
    assert "echo" in p1.route_history

    # Next forward should fail due to TTL expiring
    p2 = p1.create_forward_copy("charlie", "delta")
    assert p2 is None

    # Cyclic loop should be rejected
    p_cyclic = pkt.create_forward_copy("alpha", "echo")
    assert p_cyclic is None


def test_simpy_discrete_event_scheduling_and_loss(test_setup):
    """Verify SimPy discrete event transmission and packet record logging."""
    engine = test_setup["engine"]
    topo = test_setup["topology"]

    pkt = Packet(
        packet_id="pkt-simpy-test",
        source_id="alpha",
        destination_id="echo",
        prev_hop="alpha",
        next_hop="echo",
        msg_type="SYNC_REQ",
        priority=PRIORITY_SYNC,
        payload={"action": "test"},
    )

    initial_sent = engine.total_packets_sent
    engine.schedule_packet(pkt)
    # Step simulation clock
    engine.step(delta_sim_seconds=2.0)

    assert engine.total_packets_sent > initial_sent
    assert len(engine.transmission_log) > 0


def test_station_sqlite_offline_isolation(test_setup):
    """Verify station continues logging events to independent SQLite store during complete isolation."""
    stations = test_setup["stations"]
    topo = test_setup["topology"]

    # Cut all links
    for n1 in stations.keys():
        for n2 in stations.keys():
            if n1 != n2:
                topo.cut_link(n1, n2)

    comps = topo.get_connected_components()
    assert len(comps) == 5

    # Alpha and Charlie operate offline
    ev_a = stations["alpha"].record_local_event("need", "need-tarps", "CREATE", {"item": "Tarps", "urgency": "HIGH"})
    ev_c = stations["charlie"].record_local_event("shelter", "shelter-gym", "CREATE", {"name": "Gym", "capacity": 60})

    assert stations["alpha"].store.count() >= 1
    assert stations["charlie"].store.count() >= 1
    assert stations["alpha"].store.get_version_vector()["alpha"] == ev_a.counter
    assert stations["charlie"].store.get_version_vector()["charlie"] == ev_c.counter


def test_rescuenet_adapter_multi_hop_sync_and_convergence(test_setup):
    """
    End-to-end multi-hop synchronization test:
    1. Alpha logs missing person.
    2. Charlie is partitioned across mountain ridge.
    3. Multi-hop sync routes through Echo relay.
    4. State converges deterministically on both stations.
    """
    nodes = test_setup["nodes"]

    # Alpha records event
    ev = nodes["alpha"].record_event("person", "person-target-1", "CREATE", {"name": "Samir Khan", "status": "SAFE"})

    # Sync Alpha -> Echo, then Echo -> Charlie
    stats_ae = nodes["alpha"].sync_with("echo")
    assert stats_ae.success is True

    stats_ec = nodes["echo"].sync_with("charlie")
    assert stats_ec.success is True

    # Charlie must now have Alpha's event in its SQLite store
    state_charlie = nodes["charlie"].get_state()
    assert "person-target-1" in state_charlie.get("person", {})
    assert state_charlie["person"]["person-target-1"]["name"] == "Samir Khan"
    assert nodes["charlie"].get_version_vector()["alpha"] >= ev.counter


def test_conflict_retention_and_human_triage(test_setup):
    """Verify concurrent conflicting sightings are preserved in conflict ledger and resolved by triage."""
    nodes = test_setup["nodes"]

    # Alpha logs MISSING, Charlie logs FOUND_SAFE
    nodes["alpha"].record_event("person", "person-conflict-test", "UPDATE", {"name": "Priya Sen", "status": "MISSING", "location": "Bridge"})
    nodes["charlie"].record_event("person", "person-conflict-test", "UPDATE", {"name": "Priya Sen", "status": "FOUND_SAFE", "location": "Camp"})

    # Sync
    nodes["alpha"].sync_with("echo")
    nodes["echo"].sync_with("charlie")
    nodes["alpha"].sync_with("echo")

    state = nodes["alpha"].get_state()
    priya = state["person"]["person-conflict-test"]
    assert len(priya.get("conflicts", [])) >= 1

    # Human triage resolves
    ConflictResolver.resolve_person_conflict(
        node=nodes["alpha"],
        person_id="person-conflict-test",
        verified_status="FOUND_SAFE_VERIFIED",
        verified_location="Camp Charlie",
        resolution_notes="Triage confirmed",
    )
    nodes["alpha"].sync_with("echo")
    nodes["echo"].sync_with("charlie")

    res_state = nodes["charlie"].get_state()
    assert res_state["person"]["person-conflict-test"]["status"] == "FOUND_SAFE_VERIFIED"


def test_single_owner_boat_token_and_escrow_conservation(test_setup):
    """Verify single-owner boat exclusivity (double allocation impossible) and escrow conservation."""
    nodes = test_setup["nodes"]

    # Register Boat Titan at Alpha
    TokenManager.register_item(nodes["alpha"], "boat-titan", "Titan Flood Boat", initial_holder_id="alpha")
    # Escrow pool of 100 antibiotics
    EscrowManager.create_pool(nodes["alpha"], "supply-antibiotics", "Antibiotics", 100, {"alpha": 50, "bravo": 50})

    nodes["alpha"].sync_with("bravo")
    nodes["alpha"].sync_with("echo")
    nodes["echo"].sync_with("charlie")

    # Charlie (does NOT have token) attempts confirmed allocation -> raises UnauthorizedAllocationError
    with pytest.raises(UnauthorizedAllocationError):
        TokenManager.confirm_allocation(nodes["charlie"], "boat-titan", "Mission", "charlie")

    # Bravo consumes from its local quota
    EscrowManager.consume(nodes["bravo"], "supply-antibiotics", 20, "Patient 1")
    # Bravo attempts to over-allocate beyond remaining 30 -> raises InsufficientQuotaError
    with pytest.raises(InsufficientQuotaError):
        EscrowManager.consume(nodes["bravo"], "supply-antibiotics", 35, "Patient 2")

    # Sync and verify escrow conservation
    nodes["bravo"].sync_with("alpha")
    state = nodes["alpha"].get_state()
    sup = state["supply"]["supply-antibiotics"]
    assert sup["consumed"] == 20
    assert sum(sup["quotas"].values()) == 80
    assert sup["consumed"] + sum(sup["quotas"].values()) == 100


def test_relay_failure_and_route_recovery(test_setup):
    """Verify that destroying Echo relay causes route recomputation or reports disconnected."""
    topo = test_setup["topology"]
    stations = test_setup["stations"]

    # Echo online: route exists
    r1 = topo.get_route("alpha", "charlie")
    assert r1 is not None

    # Destroy Echo relay tower
    stations["echo"].destroy("Structural collapse")
    topo.recompute_all_links()

    # Route through Echo must no longer be viable
    r2 = topo.get_route("alpha", "charlie")
    assert r2 is None or "echo" not in r2

    # Restore Echo
    stations["echo"].restore()
    topo.recompute_all_links()
    r3 = topo.get_route("alpha", "charlie")
    assert r3 is not None


def test_security_forged_signatures_and_tamper_rejection(test_setup):
    """Verify Ed25519 digital signature tamper detection rejects forged events."""
    nodes = test_setup["nodes"]

    # Attach keyrings
    kr_a = NodeKeyring("alpha", passphrase="secret-team-key")
    kr_b = NodeKeyring("bravo", passphrase="secret-team-key")
    kr_a.register_peer("bravo", kr_b.public_key_hex)
    kr_b.register_peer("alpha", kr_a.public_key_hex)

    nodes["alpha"].set_keyring(kr_a)
    nodes["bravo"].set_keyring(kr_b)

    # Alpha records legitimate signed event
    ev = nodes["alpha"].record_event("need", "need-secure", "CREATE", {"item": "Bandages", "urgency": "HIGH"})
    assert ev.signature != ""

    # Tamper with payload
    tampered_ev = ev.__class__(
        node_id=ev.node_id,
        counter=ev.counter + 1,
        timestamp=ev.timestamp,
        entity_type=ev.entity_type,
        entity_id=ev.entity_id,
        operation=ev.operation,
        payload={"item": "Tampered Payload"},
        signature=ev.signature,  # Signature mismatch!
    )

    # Receiver filter must reject tampered event
    filtered = nodes["bravo"]._verify_and_filter_events([tampered_ev])
    assert len(filtered) == 0


def test_all_eight_scenarios_execute(test_setup):
    """Verify all 8 disaster scenarios load, cut expected links, and log initial events without crash."""
    scenarios = ScenarioEngine(
        test_setup["terrain"],
        test_setup["stations"],
        test_setup["topology"],
        test_setup["engine"],
    )

    for sc_id in SCENARIOS.keys():
        logs = scenarios.apply_scenario(sc_id)
        assert len(logs) == 1
        assert sc_id in scenarios.active_scenario.id

    scenarios.reset_to_clean_state()
    assert scenarios.active_scenario is None


def test_five_minute_hackathon_demo_script(test_setup):
    """Verify full 7-step Hackathon Demo runner end-to-end."""
    demo = HackathonDemoRunner(
        test_setup["terrain"],
        test_setup["stations"],
        test_setup["topology"],
        test_setup["engine"],
        test_setup["transport"],
    )

    r1 = demo.run_step_1_baseline_connected()
    assert r1.invariants_verified["state_convergence"] is True

    r2 = demo.run_step_2_mountain_obstruction()
    assert r2.invariants_verified["partition_detected"] is True

    r3 = demo.run_step_3_independent_offline_operations()
    assert r3.invariants_verified["offline_isolation_maintained"] is True

    r4 = demo.run_step_4_activate_echo_relay()
    assert r4.invariants_verified["route_found"] is True

    r5 = demo.run_step_5_multi_hop_delta_sync()
    assert r5.invariants_verified["sync_success"] is True

    r6 = demo.run_step_6_verify_convergence_and_invariants()
    assert r6.invariants_verified["sec_match"] is True
    assert r6.invariants_verified["zero_lost_updates"] is True
    assert r6.invariants_verified["no_double_allocation"] is True
    assert r6.invariants_verified["escrow_conserved"] is True

    r7 = demo.run_step_7_human_triage_resolution()
    assert r7.invariants_verified["conflict_resolved"] is True
    assert len(demo.step_history) == 7
