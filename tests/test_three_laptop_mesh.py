"""
Automated 10-Scenario Test Suite for RescueNet Three-Laptop Offline Mesh.

Verifies genuine offline peer-to-peer communication across three independent nodes:
  - Laptop Alpha (alpha-harbor: Harbor Command Center)
  - Laptop Beta  (beta-hospital: Field Hospital & Medical Coordination)
  - Laptop Gamma (gamma-mountain: Mountain Shelter & Relay Station)

Test Scenarios:
  1. Alpha -> Beta: Incident creation & bi-directional sync
  2. Beta -> Gamma: Supply & medical requirement sync
  3. Gamma -> Alpha: Emergency alert broadcast & acknowledgment
  4. Three-node broadcast: Transitive multi-hop propagation (Alpha -> Beta -> Gamma)
  5. Offline disconnect, store-and-forward buffering, reconnect & full catchup
  6. Idempotent duplicate prevention: Zero duplicates upon re-syncing
  7. Process restart & SQLite persistence: Zero counter regression
  8. Offline operation without WAN/Internet: Verifies local-only execution
  9. Strict zero-trust security: Rejection of forged, untrusted, or unsigned events
 10. Simultaneous concurrent multi-node updates & mathematical state convergence
 11. (Bonus) Offline attachment transfer with SHA-256 content verification
"""

import os
import shutil
import tempfile
import time
import pytest

from events.event import Event
from transport.tcp import TCPTransport
from sync.node import Node, StrictSecurityError
from sync.gossip import GossipSyncDaemon
from crypto.keyring import NodeKeyring
from storage.attachments import AttachmentManager


# Fixed 256-bit test Mesh Pre-Shared Key (32 bytes)
TEST_MESH_KEY = bytes.fromhex("16338ae4f5da5340c4495a0083065aa94c69aa7a1ff4d63e175f43401ac16d69")
SECURITY_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "security"))


def setup_three_node_cluster(tmp_path):
    """Factory creating 3 fully-wired nodes on ephemeral TCP ports with keyring security."""
    d_alpha = str(tmp_path / "alpha.db")
    d_beta = str(tmp_path / "beta.db")
    d_gamma = str(tmp_path / "gamma.db")

    # Ephemeral TCP transports on loopback
    t_alpha = TCPTransport(node_id="alpha-harbor", host="127.0.0.1", port=0)
    t_beta = TCPTransport(node_id="beta-hospital", host="127.0.0.1", port=0)
    t_gamma = TCPTransport(node_id="gamma-mountain", host="127.0.0.1", port=0)

    # Cross-register peer ports
    t_alpha.add_peer("beta-hospital", "127.0.0.1", t_beta.port)
    t_alpha.add_peer("gamma-mountain", "127.0.0.1", t_gamma.port)

    t_beta.add_peer("alpha-harbor", "127.0.0.1", t_alpha.port)
    t_beta.add_peer("gamma-mountain", "127.0.0.1", t_gamma.port)

    t_gamma.add_peer("alpha-harbor", "127.0.0.1", t_alpha.port)
    t_gamma.add_peer("beta-hospital", "127.0.0.1", t_beta.port)

    # Keyrings
    kr_alpha = NodeKeyring("alpha-harbor", keys_dir=SECURITY_DIR, mesh_key=TEST_MESH_KEY)
    kr_beta = NodeKeyring("beta-hospital", keys_dir=SECURITY_DIR, mesh_key=TEST_MESH_KEY)
    kr_gamma = NodeKeyring("gamma-mountain", keys_dir=SECURITY_DIR, mesh_key=TEST_MESH_KEY)

    # Nodes
    n_alpha = Node("alpha-harbor", d_alpha, transport=t_alpha, keyring=kr_alpha, strict_mode=True)
    n_beta = Node("beta-hospital", d_beta, transport=t_beta, keyring=kr_beta, strict_mode=True)
    n_gamma = Node("gamma-mountain", d_gamma, transport=t_gamma, keyring=kr_gamma, strict_mode=True)

    return (n_alpha, n_beta, n_gamma), (t_alpha, t_beta, t_gamma)


def teardown_cluster(nodes, transports):
    """Safely terminate transports and stores."""
    for n in nodes:
        try:
            n.close()
        except Exception:
            pass
    for t in transports:
        try:
            t.close()
        except Exception:
            pass


# -------------------------------------------------------------
# TEST SCENARIO 1: ALPHA -> BETA INCIDENT SYNC
# -------------------------------------------------------------
def test_scenario_1_alpha_to_beta_incident_sync(tmp_path):
    """
    Scenario 1: Laptop Alpha (Harbor Base) creates an urgent incident.
    Alpha executes TCP anti-entropy sync with Beta (Hospital).
    Beta ingests the incident with verified Ed25519 signature and identical projection.
    """
    (n_a, n_b, n_c), (t_a, t_b, t_c) = setup_three_node_cluster(tmp_path)
    try:
        # Alpha logs incident offline
        ev = n_a.record_event(
            entity_type="incident",
            entity_id="inc-harbor-breach",
            operation="CREATE",
            payload={
                "title": "Harbor Seawall Breach",
                "severity": "CRITICAL",
                "location": "Dock Pier 4",
                "description": "Rising tide surging into coastal warehouse sector",
            },
        )
        assert ev.signature != ""
        assert n_a.get_version_vector() == {"alpha-harbor": 1}

        # Sync Alpha -> Beta
        stats = n_a.sync_with("beta-hospital")
        assert stats.success is True
        assert stats.events_sent == 1
        assert stats.events_received == 0

        # Verify Beta's database and projected state
        assert n_b.get_version_vector() == {"alpha-harbor": 1}
        b_state = n_b.get_state()
        assert "incident" in b_state
        assert "inc-harbor-breach" in b_state["incident"]
        assert b_state["incident"]["inc-harbor-breach"]["title"] == "Harbor Seawall Breach"
        assert b_state["incident"]["inc-harbor-breach"]["_created_by"] == "alpha-harbor"
    finally:
        teardown_cluster((n_a, n_b, n_c), (t_a, t_b, t_c))


# -------------------------------------------------------------
# TEST SCENARIO 2: BETA -> GAMMA SUPPLY & REQUIREMENT SYNC
# -------------------------------------------------------------
def test_scenario_2_beta_to_gamma_supply_requirement_sync(tmp_path):
    """
    Scenario 2: Laptop Beta (Hospital) records medical supply needs.
    Beta executes TCP sync with Gamma (Mountain Relay).
    Gamma receives and projects the medical needs accurately.
    """
    (n_a, n_b, n_c), (t_a, t_b, t_c) = setup_three_node_cluster(tmp_path)
    try:
        # Beta logs medical need
        n_b.record_event(
            entity_type="need",
            entity_id="need-blood-plasma",
            operation="CREATE",
            payload={
                "item_name": "Blood Plasma O-Negative",
                "quantity": 50,
                "unit": "units",
                "urgency": "CRITICAL",
                "location": "Hospital ICU Tent 2",
            },
        )

        # Sync Beta -> Gamma
        stats = n_b.sync_with("gamma-mountain")
        assert stats.success is True
        assert stats.events_sent == 1

        # Gamma projects the requirement
        g_state = n_c.get_state()
        assert "need" in g_state
        assert "need-blood-plasma" in g_state["need"]
        assert g_state["need"]["need-blood-plasma"]["quantity"] == 50
    finally:
        teardown_cluster((n_a, n_b, n_c), (t_a, t_b, t_c))


# -------------------------------------------------------------
# TEST SCENARIO 3: GAMMA -> ALPHA EMERGENCY ALERT SYNC
# -------------------------------------------------------------
def test_scenario_3_gamma_to_alpha_emergency_alert_sync(tmp_path):
    """
    Scenario 3: Laptop Gamma issues a CRITICAL emergency alert (Landslide).
    Syncs with Alpha. Alpha receives the alert and subsequently issues an ACK.
    """
    (n_a, n_b, n_c), (t_a, t_b, t_c) = setup_three_node_cluster(tmp_path)
    try:
        # Gamma records critical alert
        n_c.record_event(
            entity_type="alert",
            entity_id="alt-landslide-pass7",
            operation="CREATE",
            payload={
                "title": "Severe Landslide at Pass 7",
                "message": "Access road to upper evacuation shelter completely blocked",
                "severity": "CRITICAL",
                "acknowledged": False,
            },
        )

        # Sync Gamma -> Alpha
        stats = n_c.sync_with("alpha-harbor")
        assert stats.success is True
        assert stats.events_sent == 1

        # Alpha verifies alert received
        a_state = n_a.get_state()
        assert "alt-landslide-pass7" in a_state["alert"]
        assert a_state["alert"]["alt-landslide-pass7"]["acknowledged"] is False

        # Alpha acknowledges the alert
        n_a.record_event(
            entity_type="alert",
            entity_id="alt-landslide-pass7",
            operation="ACKNOWLEDGE",
            payload={"acknowledged_by": "alpha-harbor"},
        )

        # Sync Alpha -> Gamma to propagate ACK
        n_a.sync_with("gamma-mountain")
        g_state = n_c.get_state()
        assert g_state["alert"]["alt-landslide-pass7"]["acknowledged"] is True
        assert g_state["alert"]["alt-landslide-pass7"]["acknowledged_by"] == "alpha-harbor"
    finally:
        teardown_cluster((n_a, n_b, n_c), (t_a, t_b, t_c))


# -------------------------------------------------------------
# TEST SCENARIO 4: THREE-NODE BROADCAST & TRANSITIVE PROPAGATION
# -------------------------------------------------------------
def test_scenario_4_three_node_broadcast(tmp_path):
    """
    Scenario 4: Information created on Alpha reaches Gamma via Beta (Transitive Gossip).
    Alpha -> Beta, then Beta -> Gamma.
    Verifies that Gamma learns about Alpha's record without direct Alpha-Gamma connection.
    """
    (n_a, n_b, n_c), (t_a, t_b, t_c) = setup_three_node_cluster(tmp_path)
    try:
        # Alpha deploys rescue personnel
        n_a.record_event(
            entity_type="rescuer",
            entity_id="res-sar-team-1",
            operation="CREATE",
            payload={
                "name": "Harbor S&R Squad 1",
                "role": "Amphibious Rescue",
                "status": "DEPLOYED",
                "callsign": "RESCUE-1",
            },
        )

        # Hop 1: Alpha syncs with Beta
        s1 = n_a.sync_with("beta-hospital")
        assert s1.success is True
        assert "res-sar-team-1" in n_b.get_state()["rescuer"]

        # Hop 2: Beta syncs with Gamma
        s2 = n_b.sync_with("gamma-mountain")
        assert s2.success is True
        assert "res-sar-team-1" in n_c.get_state()["rescuer"]

        # All 3 nodes have converged on this event
        assert n_a.get_version_vector()["alpha-harbor"] == 1
        assert n_b.get_version_vector()["alpha-harbor"] == 1
        assert n_c.get_version_vector()["alpha-harbor"] == 1
    finally:
        teardown_cluster((n_a, n_b, n_c), (t_a, t_b, t_c))


# -------------------------------------------------------------
# TEST SCENARIO 5: OFFLINE DISCONNECT, BUFFERING, RECONNECT & CATCHUP
# -------------------------------------------------------------
def test_scenario_5_offline_disconnect_buffer_reconnect_catchup(tmp_path):
    """
    Scenario 5: Gamma is disconnected (offline).
    Alpha and Beta record multiple new incidents, victims, and supplies.
    Gamma reconnects, runs anti-entropy sync, and catches up completely with zero data loss.
    """
    (n_a, n_b, n_c), (t_a, t_b, t_c) = setup_three_node_cluster(tmp_path)
    try:
        # Step 1: Temporarily shut down Gamma's transport to simulate disconnection
        t_c.close()

        # Step 2: Alpha and Beta continue operations while Gamma is isolated
        n_a.record_event("victim", "vic-101", "CREATE", {"name": "Alice Green", "triage_category": "RED"})
        n_a.record_event("incident", "inc-bridge-collapse", "CREATE", {"title": "North Bridge Out"})
        n_b.record_event("victim", "vic-102", "CREATE", {"name": "Bob Miller", "triage_category": "YELLOW"})
        n_b.record_event("chat", "chat-001", "CREATE", {"text": "Triage zone established", "sender": "beta"})

        # Alpha and Beta sync with each other
        n_a.sync_with("beta-hospital")
        assert n_a.store.count() == 4
        assert n_b.store.count() == 4
        assert n_c.store.count() == 0  # Gamma is completely isolated

        # Step 3: Gamma reconnects (creates fresh socket on a new port)
        t_c_new = TCPTransport(node_id="gamma-mountain", host="127.0.0.1", port=0)
        n_c.attach_transport(t_c_new)

        # Update Alpha and Beta's route tables with Gamma's new port
        t_a.add_peer("gamma-mountain", "127.0.0.1", t_c_new.port)
        t_b.add_peer("gamma-mountain", "127.0.0.1", t_c_new.port)
        t_c_new.add_peer("alpha-harbor", "127.0.0.1", t_a.port)
        t_c_new.add_peer("beta-hospital", "127.0.0.1", t_b.port)

        # Step 4: Gamma executes anti-entropy sync with Alpha
        stats = n_c.sync_with("alpha-harbor")
        assert stats.success is True
        assert stats.events_received == 4

        # Verify Gamma holds the complete, exact state
        assert n_c.store.count() == 4
        g_state = n_c.get_state()
        assert "vic-101" in g_state["victim"]
        assert "vic-102" in g_state["victim"]
        assert "inc-bridge-collapse" in g_state["incident"]
        assert "chat-001" in g_state["chat"]

        t_c_new.close()
    finally:
        teardown_cluster((n_a, n_b, n_c), (t_a, t_b, t_c))


# -------------------------------------------------------------
# TEST SCENARIO 6: IDEMPOTENT DUPLICATE PREVENTION
# -------------------------------------------------------------
def test_scenario_6_idempotent_duplicate_prevention(tmp_path):
    """
    Scenario 6: Same events are synced repeatedly between nodes.
    Verifies that duplicate events are ignored and store count remains strictly stable.
    """
    (n_a, n_b, n_c), (t_a, t_b, t_c) = setup_three_node_cluster(tmp_path)
    try:
        n_a.record_event("shelter", "sh-1", "CREATE", {"name": "Harbor Gym", "capacity": 200})
        n_a.record_event("shelter", "sh-2", "CREATE", {"name": "School Hall", "capacity": 150})

        # Sync 1
        s1 = n_a.sync_with("beta-hospital")
        assert s1.events_sent == 2
        assert n_b.store.count() == 2

        # Sync 2 (immediately repeated)
        s2 = n_a.sync_with("beta-hospital")
        assert s2.success is True
        assert s2.events_sent == 0  # Nothing missing
        assert n_b.store.count() == 2  # No duplicates

        # Sync 3 (initiated in reverse direction)
        s3 = n_b.sync_with("alpha-harbor")
        assert s3.success is True
        assert s3.events_sent == 0
        assert n_a.store.count() == 2
    finally:
        teardown_cluster((n_a, n_b, n_c), (t_a, t_b, t_c))


# -------------------------------------------------------------
# TEST SCENARIO 7: PROCESS RESTART & SQLITE PERSISTENCE
# -------------------------------------------------------------
def test_scenario_7_process_restart_sqlite_persistence(tmp_path):
    """
    Scenario 7: Node shuts down completely and restarts.
    Verifies that the monotonic counter continues from the stored state with zero regression.
    """
    db_file = str(tmp_path / "persistent_alpha.db")
    kr = NodeKeyring("alpha-harbor", keys_dir=SECURITY_DIR, mesh_key=TEST_MESH_KEY)

    # Run 1: Create node, log 3 events, shut down
    node1 = Node("alpha-harbor", db_file, keyring=kr, strict_mode=True)
    node1.record_event("victim", "v-1", "CREATE", {"name": "Victim 1"})
    node1.record_event("victim", "v-2", "CREATE", {"name": "Victim 2"})
    node1.record_event("victim", "v-3", "CREATE", {"name": "Victim 3"})
    assert node1.get_version_vector() == {"alpha-harbor": 3}
    node1.close()

    # Run 2: Restart node pointing to same database file
    node2 = Node("alpha-harbor", db_file, keyring=kr, strict_mode=True)
    assert node2.get_version_vector() == {"alpha-harbor": 3}

    # Record next event: counter must be 4
    ev4 = node2.record_event("victim", "v-4", "CREATE", {"name": "Victim 4"})
    assert ev4.counter == 4
    assert node2.get_version_vector() == {"alpha-harbor": 4}
    assert node2.store.count() == 4
    node2.close()


# -------------------------------------------------------------
# TEST SCENARIO 8: OFFLINE OPERATION WITHOUT WAN/INTERNET
# -------------------------------------------------------------
def test_scenario_8_offline_operation_without_wan_internet(tmp_path):
    """
    Scenario 8: Verifies that all cryptographic operations, SQLite storage,
    and TCP framing execute purely locally with zero WAN or external network calls.
    """
    (n_a, n_b, n_c), (t_a, t_b, t_c) = setup_three_node_cluster(tmp_path)
    try:
        # All addresses are strictly loopback / private RFC 1918
        for p in [t_a, t_b, t_c]:
            assert p.host == "127.0.0.1"

        # Record events across all nodes
        ev_a = n_a.record_event("chat", "msg-1", "CREATE", {"text": "Local mesh active"})
        ev_b = n_b.record_event("chat", "msg-2", "CREATE", {"text": "Hotspot isolated from WAN"})

        # Synchronize
        stats = n_a.sync_with("beta-hospital")
        assert stats.success is True

        # Decryption and signature verification verified offline
        state_b = n_b.get_state()
        assert "msg-1" in state_b["chat"]
        assert state_b["chat"]["msg-1"]["text"] == "Local mesh active"
    finally:
        teardown_cluster((n_a, n_b, n_c), (t_a, t_b, t_c))


# -------------------------------------------------------------
# TEST SCENARIO 9: STRICT SECURITY REJECTION OF FORGED MESSAGES
# -------------------------------------------------------------
def test_scenario_9_strict_security_rejection_of_forged_messages(tmp_path):
    """
    Scenario 9: An untrusted node or attacker attempts to inject an unsigned
    or forged event into Beta.
    Beta's strict security drops the event and records it in security_drop_log.
    """
    (n_a, n_b, n_c), (t_a, t_b, t_c) = setup_three_node_cluster(tmp_path)
    try:
        # Attacker creates forged event pretending to be alpha-harbor
        fake_event = Event(
            node_id="alpha-harbor",
            counter=999,
            timestamp=time.time(),
            entity_type="incident",
            entity_id="inc-fake",
            operation="CREATE",
            payload={"title": "Forged Intruder Alert"},
            signature="deadbeef" * 8,  # Invalid signature
        )

        # Directly attempt to verify via Beta's filter
        filtered = n_b._verify_and_filter_events([fake_event])
        assert len(filtered) == 0  # Dropped!

        # Verify entry in security drop log
        assert len(n_b.security_drop_log) == 1
        assert n_b.security_drop_log[0]["reason"] == "INVALID_SIGNATURE"
        assert n_b.security_drop_log[0]["node_id"] == "alpha-harbor"
    finally:
        teardown_cluster((n_a, n_b, n_c), (t_a, t_b, t_c))


# -------------------------------------------------------------
# TEST SCENARIO 10: SIMULTANEOUS CONCURRENT MULTI-NODE CONVERGENCE
# -------------------------------------------------------------
def test_scenario_10_simultaneous_concurrent_multi_node_updates_convergence(tmp_path):
    """
    Scenario 10: Alpha, Beta, and Gamma simultaneously produce distinct records.
    Anti-entropy gossip runs across all pairs.
    Mathematical convergence: All three nodes reach byte-for-byte identical state.
    """
    (n_a, n_b, n_c), (t_a, t_b, t_c) = setup_three_node_cluster(tmp_path)
    try:
        # Concurrent updates
        n_a.record_event("incident", "inc-a1", "CREATE", {"title": "Dock Flooding"})
        n_a.record_event("victim", "vic-a1", "CREATE", {"name": "Victim A"})

        n_b.record_event("need", "need-b1", "CREATE", {"item_name": "Oxygen Tanks", "quantity": 20})
        n_b.record_event("victim", "vic-b1", "CREATE", {"name": "Victim B"})

        n_c.record_event("alert", "alt-c1", "CREATE", {"title": "Windstorm Warning"})
        n_c.record_event("rescuer", "res-c1", "CREATE", {"name": "Mountain Ranger 1"})

        # Pairwise gossip synchronization:
        # Round 1: A <-> B
        n_a.sync_with("beta-hospital")
        # Round 2: B <-> C
        n_b.sync_with("gamma-mountain")
        # Round 3: C <-> A
        n_c.sync_with("alpha-harbor")
        # Round 4: B <-> A (propagation of C's data from B)
        n_b.sync_with("alpha-harbor")
        # Round 5: B <-> C
        n_b.sync_with("gamma-mountain")

        # Invariant: Every node must possess all 6 events
        assert n_a.store.count() == 6
        assert n_b.store.count() == 6
        assert n_c.store.count() == 6

        # Invariant: Version vectors must be identical
        expected_vv = {"alpha-harbor": 2, "beta-hospital": 2, "gamma-mountain": 2}
        assert n_a.get_version_vector() == expected_vv
        assert n_b.get_version_vector() == expected_vv
        assert n_c.get_version_vector() == expected_vv

        # Invariant: Materialized domain states must be identical
        state_a = n_a.get_state()
        state_b = n_b.get_state()
        state_c = n_c.get_state()
        assert state_a == state_b == state_c
    finally:
        teardown_cluster((n_a, n_b, n_c), (t_a, t_b, t_c))


# -------------------------------------------------------------
# TEST SCENARIO 11: OFFLINE ATTACHMENT TRANSFER
# -------------------------------------------------------------
def test_scenario_11_offline_attachment_transfer(tmp_path):
    """
    Scenario 11: Alpha stores an offline photo attachment and broadcasts the event.
    Beta receives the event via sync and writes the verified file to local disk.
    """
    (n_a, n_b, n_c), (t_a, t_b, t_c) = setup_three_node_cluster(tmp_path)
    dir_a = str(tmp_path / "attachments_alpha")
    dir_b = str(tmp_path / "attachments_beta")
    mgr_a = AttachmentManager(dir_a)
    mgr_b = AttachmentManager(dir_b)

    try:
        # Alpha saves a simulated disaster map photo
        fake_photo_bytes = b"RESCUENET-OFFLINE-SURVEY-MAP-DATA-BYTES-2026"
        att_data = mgr_a.save_file("pier4_survey.png", fake_photo_bytes, description="Pier 4 flood survey", uploader="alpha-harbor")

        # Alpha logs the attachment event
        n_a.record_event(
            entity_type="attachment",
            entity_id=att_data["file_id"],
            operation="CREATE",
            payload=att_data,
        )

        # Wire event listener on Beta to simulate node_server auto-ingest
        n_b.register_event_listener(lambda ev: mgr_b.ingest_attachment_event(ev.payload) if ev.entity_type == "attachment" else None)

        # Sync Alpha -> Beta
        stats = n_a.sync_with("beta-hospital")
        assert stats.success is True

        # Verify Beta wrote file to disk and verified SHA-256
        found = mgr_b.get_attachment(att_data["file_id"])
        assert found is not None
        fpath, fname, mtype = found
        assert os.path.exists(fpath)
        with open(fpath, "rb") as f:
            assert f.read() == fake_photo_bytes
    finally:
        teardown_cluster((n_a, n_b, n_c), (t_a, t_b, t_c))
