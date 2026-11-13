"""
Tests for Autonomous Anti-Entropy Gossip Synchronization, Partition Reconnection, and Multi-Hop Propagation.
"""

from __future__ import annotations
import time
import pytest
from sync.node import Node
from sync.gossip import GossipSyncDaemon
from transport.in_memory import InMemoryTransport


def test_gossip_daemon_lifecycle():
    transport = InMemoryTransport()
    node = Node("node-1", db_path=":memory:", transport=transport)

    daemon = GossipSyncDaemon(node=node, interval_sec=0.2, peers=["node-2"])
    daemon.start()
    assert daemon._is_running is True
    assert daemon._thread is not None
    assert daemon._thread.is_alive()

    daemon.stop(timeout=1.0)
    assert daemon._is_running is False
    assert not daemon._thread.is_alive()
    node.close()


def test_gossip_autonomous_sync():
    transport = InMemoryTransport()
    node_a = Node("node-A", db_path=":memory:", transport=transport)
    node_b = Node("node-B", db_path=":memory:", transport=transport)

    # Node A produces an event
    node_a.record_event("need", "need-1", "CREATE", {"item": "Water Bottles", "urgency": "HIGH"})
    assert node_a.store.count() == 1
    assert node_b.store.count() == 0

    # Start gossip daemon on Node A targeting Node B
    node_a.start_gossip(interval_sec=0.1, peers=["node-B"])

    # Wait for at least one gossip tick
    deadline = time.time() + 2.0
    while time.time() < deadline:
        if node_b.store.count() >= 1:
            break
        time.sleep(0.05)

    assert node_b.store.count() == 1
    assert node_b.get_version_vector() == {"node-A": 1}

    # Verify peer health
    health = node_a.get_peer_health()
    assert "node-B" in health
    assert health["node-B"]["status"] == "ONLINE"
    assert health["node-B"]["total_events_sent"] >= 1

    node_a.close()
    node_b.close()


def test_gossip_partition_and_reconnection():
    transport = InMemoryTransport()
    node_a = Node("node-A", db_path=":memory:", transport=transport)
    node_b = Node("node-B", db_path=":memory:", transport=transport)

    node_a.start_gossip(interval_sec=0.1, peers=["node-B"])

    # Initial sync
    node_a.record_event("shelter", "sh-1", "CREATE", {"name": "Central High", "capacity": 200})
    deadline = time.time() + 2.0
    while time.time() < deadline:
        if node_b.store.count() == 1:
            break
        time.sleep(0.05)
    assert node_b.store.count() == 1

    # Simulate network partition: cut link between A and B
    transport.cut_link("node-A", "node-B")

    # Node A produces event while partitioned
    node_a.record_event("shelter", "sh-2", "CREATE", {"name": "Civic Center", "capacity": 150})
    assert node_a.store.count() == 2

    # Wait for gossip attempt to fail
    time.sleep(0.3)
    health = node_a.get_peer_health()
    assert health["node-B"]["status"] == "UNREACHABLE"
    assert health["node-B"]["consecutive_failures"] >= 1
    assert node_b.store.count() == 1  # Node B hasn't received sh-2 yet

    # Heal network link
    transport.heal_link("node-A", "node-B")

    # Gossip should detect link reconnection and sync sh-2 automatically
    deadline = time.time() + 2.0
    while time.time() < deadline:
        if node_b.store.count() == 2:
            break
        time.sleep(0.05)

    assert node_b.store.count() == 2
    assert node_b.get_version_vector() == {"node-A": 2}
    health_recovered = node_a.get_peer_health()
    assert health_recovered["node-B"]["status"] == "ONLINE"

    node_a.close()
    node_b.close()


def test_gossip_multi_hop_transitive_propagation():
    """
    Test line topology: A <-> B <-> C (A is partitioned from direct contact with C).
    Events created on A propagate transitively to C via B's gossip worker.
    """
    transport = InMemoryTransport()
    # Direct link between A-B and B-C, but A-C is cut
    transport.cut_link("node-A", "node-C")

    node_a = Node("node-A", db_path=":memory:", transport=transport)
    node_b = Node("node-B", db_path=":memory:", transport=transport)
    node_c = Node("node-C", db_path=":memory:", transport=transport)

    # Start gossip daemons on all three nodes
    node_a.start_gossip(interval_sec=0.1, peers=["node-B"])
    node_b.start_gossip(interval_sec=0.1, peers=["node-A", "node-C"])
    node_c.start_gossip(interval_sec=0.1, peers=["node-B"])

    # Node A generates an emergency SOS event
    node_a.record_event("need", "sos-1", "CREATE", {"item": "Rescue Boat", "urgency": "CRITICAL"})

    # Wait for transitive multi-hop propagation: A -> B -> C
    deadline = time.time() + 3.0
    while time.time() < deadline:
        if node_c.store.count() >= 1:
            break
        time.sleep(0.05)

    assert node_c.store.count() == 1
    assert node_c.get_version_vector()["node-A"] == 1

    ev_at_c = node_c.store.get_event(node_a.store.get_all_events()[0].event_id)
    assert ev_at_c is not None
    assert ev_at_c.payload["urgency"] == "CRITICAL"

    node_a.close()
    node_b.close()
    node_c.close()
