"""
Unit and Integration Tests for Stage 7:
TCP Transport (Local Wi-Fi / Hotspot Mesh) and BLE Stub.
"""

import time
import pytest
from transport.tcp import TCPTransport
from transport.ble_stub import BLEStubTransport
from sync.node import Node


def test_tcp_transport_framing_and_two_node_sync():
    """Verify point-to-point anti-entropy sync over real TCP sockets using ephemeral ports."""
    t_alpha = TCPTransport(node_id="node-alpha", host="127.0.0.1", port=0)
    t_beta = TCPTransport(node_id="node-beta", host="127.0.0.1", port=0)

    # Cross-register peer ports
    t_alpha.add_peer("node-beta", "127.0.0.1", t_beta.port)
    t_beta.add_peer("node-alpha", "127.0.0.1", t_alpha.port)

    node_alpha = Node("node-alpha", ":memory:", t_alpha)
    node_beta = Node("node-beta", ":memory:", t_beta)

    # Node Alpha records offline event
    node_alpha.record_event("shelter", "sh-1", "CREATE", {"name": "Red Cross Tent", "capacity": 100})
    # Node Beta records offline event
    node_beta.record_event("need", "nd-1", "CREATE", {"item": "Generators", "urgency": "HIGH"})

    # Perform TCP sync initiated by Alpha
    stats = node_alpha.sync_with("node-beta")

    assert stats.success is True
    assert stats.events_sent == 1
    assert stats.events_received == 1
    assert stats.total_bytes > 0

    # Verify state convergence over TCP
    assert node_alpha.get_version_vector() == {"node-alpha": 1, "node-beta": 1}
    assert node_beta.get_version_vector() == {"node-alpha": 1, "node-beta": 1}
    assert node_alpha.get_state() == node_beta.get_state()

    # Wire telemetry was recorded
    assert t_alpha.get_stats()["total_bytes"] > 0
    assert t_beta.get_stats()["total_bytes"] > 0

    t_alpha.close()
    t_beta.close()
    node_alpha.close()
    node_beta.close()


def test_three_tcp_nodes_local_mesh_convergence():
    """
    Requirement 7: 3 nodes (representing 3 laptops on a hotspot with internet off)
    synchronizing transitively over real TCP sockets.
    """
    t_a = TCPTransport("node-A", "127.0.0.1", port=0)
    t_b = TCPTransport("node-B", "127.0.0.1", port=0)
    t_c = TCPTransport("node-C", "127.0.0.1", port=0)

    # Setup 3-node peer directory
    t_a.add_peer("node-B", "127.0.0.1", t_b.port)
    t_a.add_peer("node-C", "127.0.0.1", t_c.port)

    t_b.add_peer("node-A", "127.0.0.1", t_a.port)
    t_b.add_peer("node-C", "127.0.0.1", t_c.port)

    t_c.add_peer("node-A", "127.0.0.1", t_a.port)
    t_c.add_peer("node-B", "127.0.0.1", t_b.port)

    node_a = Node("node-A", ":memory:", t_a)
    node_b = Node("node-B", ":memory:", t_b)
    node_c = Node("node-C", ":memory:", t_c)

    # Each node generates a local record with NO internet
    node_a.record_event("shelter", "shelter-harbor", "CREATE", {"capacity": 300})
    node_b.record_event("supply", "plasma-crate", "CREATE", {"quantity": 80})
    node_c.record_event("person", "person-dr-maya", "CREATE", {"name": "Dr. Maya", "status": "ON_DUTY"})

    # Pairwise TCP sync: A -> B, then B -> C, then C -> A
    stats_ab = node_a.sync_with("node-B")
    assert stats_ab.success is True

    stats_bc = node_b.sync_with("node-C")
    assert stats_bc.success is True

    stats_ca = node_c.sync_with("node-A")
    assert stats_ca.success is True

    # One final sweep to ensure full 3-node closure
    node_a.sync_with("node-B")

    # All 3 nodes must have converged to identical state over TCP!
    state_a = node_a.get_state()
    state_b = node_b.get_state()
    state_c = node_c.get_state()

    assert state_a == state_b == state_c
    assert "shelter-harbor" in state_a["shelter"]
    assert "plasma-crate" in state_a["supply"]
    assert "person-dr-maya" in state_a["person"]

    t_a.close()
    t_b.close()
    t_c.close()
    node_a.close()
    node_b.close()
    node_c.close()


def test_tcp_peer_offline_fails_gracefully():
    """Verify that attempting to sync with an offline peer times out safely."""
    # Node Alpha is online
    t_alpha = TCPTransport("node-alpha", "127.0.0.1", port=0, timeout=0.5)
    # Register an unused high port (no server running)
    t_alpha.add_peer("node-offline", "127.0.0.1", 59998)
    node_alpha = Node("node-alpha", ":memory:", t_alpha)

    # Sync attempt should fail gracefully without crashing
    stats = node_alpha.sync_with("node-offline")

    assert stats.success is False
    assert "unreachable" in stats.error.lower()
    assert stats.events_sent == 0
    assert stats.events_received == 0

    t_alpha.close()
    node_alpha.close()


def test_ble_stub_interface_compliance():
    """Verify BLE stub implements the Transport interface."""
    ble = BLEStubTransport("node-phone")
    assert ble.node_id == "node-phone"
    assert ble.send(None) is None
    assert ble.get_stats()["total_bytes"] == 0
