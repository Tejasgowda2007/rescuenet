"""
Unit and Integration Tests for Stage 2:
Version-Vector Anti-Entropy Sync between In-Memory Nodes with Byte Counting.
"""

import pytest
from transport.in_memory import InMemoryTransport
from sync.node import Node


def test_two_nodes_bi_directional_sync_and_convergence():
    """
    Test two offline nodes meeting, exchanging version vectors,
    sending only missing events, and converging to identical state.
    """
    transport = InMemoryTransport()
    node_a = Node("node-A", ":memory:", transport)
    node_b = Node("node-B", ":memory:", transport)

    # Node A operates offline: logs 3 events
    node_a.record_event("shelter", "sh-1", "CREATE", {"name": "Civic Center", "capacity": 500})
    node_a.record_event("supply", "sp-1", "CREATE", {"item": "Blankets", "quantity": 200})
    node_a.record_event("person", "p-1", "CREATE", {"name": "Alice Cooper", "status": "MISSING"})

    # Node B operates offline: logs 2 events
    node_b.record_event("need", "nd-1", "CREATE", {"desc": "Water purification tablets", "urgency": "HIGH"})
    node_b.record_event("person", "p-1", "UPDATE", {"status": "FOUND_SAFE", "shelter": "sh-1"})

    # Check pre-sync states
    assert node_a.store.count() == 3
    assert node_b.store.count() == 2
    assert node_a.get_version_vector() == {"node-A": 3}
    assert node_b.get_version_vector() == {"node-B": 2}

    # Execute bi-directional sync initiated by Node A
    stats = node_a.sync_with("node-B")

    # Verify telemetry
    assert stats.success is True
    assert stats.events_sent == 3      # Node A sent its 3 events
    assert stats.events_received == 2  # Node A received Node B's 2 events
    assert stats.bytes_sent > 0
    assert stats.bytes_received > 0
    assert stats.total_bytes == stats.bytes_sent + stats.bytes_received

    # Verify convergence: both have 5 events and identical version vectors
    assert node_a.store.count() == 5
    assert node_b.store.count() == 5
    assert node_a.get_version_vector() == {"node-A": 3, "node-B": 2}
    assert node_b.get_version_vector() == {"node-A": 3, "node-B": 2}

    # Verify domain state convergence
    state_a = node_a.get_state()
    state_b = node_b.get_state()
    assert state_a == state_b

    # Verify conflict tracking preserved
    person_a = state_a["person"]["p-1"]
    assert person_a["status"] == "FOUND_SAFE"
    assert len(person_a["conflicts"]) == 1

    node_a.close()
    node_b.close()


def test_subsequent_sync_transfers_zero_events_and_minimal_bytes():
    """
    Requirement 4: Sync payloads must be small (only send what the other side is missing).
    A follow-up sync between two converged nodes must transmit 0 events.
    """
    transport = InMemoryTransport()
    node_a = Node("node-A", ":memory:", transport)
    node_b = Node("node-B", ":memory:", transport)

    # 1 event each
    node_a.record_event("shelter", "sh-1", "CREATE", {"capacity": 100})
    node_b.record_event("supply", "sp-1", "CREATE", {"quantity": 50})

    # First sync (exchanges events)
    first_stats = node_a.sync_with("node-B")
    assert first_stats.events_sent == 1
    assert first_stats.events_received == 1

    # Second sync immediately following (both already have all events)
    second_stats = node_a.sync_with("node-B")
    assert second_stats.success is True
    assert second_stats.events_sent == 0
    assert second_stats.events_received == 0

    # Wire bytes in second sync should be strictly less than first sync
    assert second_stats.total_bytes < first_stats.total_bytes

    node_a.close()
    node_b.close()


def test_network_partition_handling():
    """
    Test that sync gracefully reports failure during a partition,
    and resumes cleanly once the partition heals.
    """
    transport = InMemoryTransport()
    node_a = Node("node-A", ":memory:", transport)
    node_b = Node("node-B", ":memory:", transport)

    node_a.record_event("need", "nd-1", "CREATE", {"item": "Food rations"})

    # Cut link between A and B
    transport.cut_link("node-A", "node-B")

    # Attempt sync during split
    split_stats = node_a.sync_with("node-B")
    assert split_stats.success is False
    assert "unreachable" in split_stats.error.lower()
    assert node_b.store.count() == 0  # Node B still knows nothing

    # Heal network link
    transport.heal_link("node-A", "node-B")

    # Sync now succeeds
    heal_stats = node_a.sync_with("node-B")
    assert heal_stats.success is True
    assert heal_stats.events_sent == 1
    assert node_b.store.count() == 1

    node_a.close()
    node_b.close()


def test_transitive_gossip_sync_three_nodes():
    """
    Node A meets Node B; Node B then travels and meets Node C.
    Node C must receive Node A's events transitively via Node B without ever meeting Node A!
    """
    transport = InMemoryTransport()
    node_a = Node("node-A", ":memory:", transport)
    node_b = Node("node-B", ":memory:", transport)
    node_c = Node("node-C", ":memory:", transport)

    # Node A creates event
    node_a.record_event("shelter", "sh-central", "CREATE", {"name": "Central Depot"})

    # Node A syncs with Node B
    node_a.sync_with("node-B")
    assert node_b.store.count() == 1

    # Node B travels and syncs with Node C (Node A is nowhere nearby)
    node_b.sync_with("node-C")
    assert node_c.store.count() == 1

    # Node C now holds Node A's event!
    state_c = node_c.get_state()
    assert "sh-central" in state_c["shelter"]
    assert state_c["shelter"]["sh-central"]["name"] == "Central Depot"

    node_a.close()
    node_b.close()
    node_c.close()
