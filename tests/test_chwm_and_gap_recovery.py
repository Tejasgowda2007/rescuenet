"""
Tests for Contiguous High-Water Mark (CHWM), Gap Detection, and Anti-Entropy Gap Recovery.
"""

from __future__ import annotations
import pytest
from events.event import Event
from storage.sqlite_store import SQLiteEventStore
from sync.node import Node
from transport.in_memory import InMemoryTransport


def test_chwm_basic_and_gaps():
    store = SQLiteEventStore(":memory:")
    # Create events with deliberate gaps: 1, 2, 4, 5, 8
    events = [
        Event("node-A", 1, 10.0, "need", "n1", "CREATE", {"item": "Water"}),
        Event("node-A", 2, 20.0, "need", "n2", "CREATE", {"item": "Food"}),
        Event("node-A", 4, 40.0, "need", "n4", "CREATE", {"item": "Tarps"}),
        Event("node-A", 5, 50.0, "need", "n5", "CREATE", {"item": "Cots"}),
        Event("node-A", 8, 80.0, "need", "n8", "CREATE", {"item": "Medkits"}),
    ]
    for ev in events:
        store.append(ev)

    # Contiguous high water mark should be 2 because 3 is missing
    chwm = store.get_contiguous_high_water_mark("node-A")
    assert chwm == 2

    # Max counter seen is 8
    max_c = store.get_max_counter("node-A")
    assert max_c == 8

    # Missing counter ranges should be [3, 3] and [6, 7]
    gaps = store.get_missing_counter_ranges("node-A")
    assert gaps == [(3, 3), (6, 7)]

    # All gaps across store
    all_gaps = store.get_all_gaps()
    assert all_gaps == {"node-A": [(3, 3), (6, 7)]}

    # Version vector advertises the CHWM
    vv = store.get_version_vector()
    assert vv == {"node-A": 2}

    # Max version vector returns raw max
    max_vv = store.get_max_version_vector()
    assert max_vv == {"node-A": 8}

    store.close()


def test_chwm_counter_1_missing():
    store = SQLiteEventStore(":memory:")
    # Events starting from counter 2 (counter 1 missing)
    events = [
        Event("node-B", 2, 20.0, "shelter", "s1", "CREATE", {"name": "School"}),
        Event("node-B", 3, 30.0, "shelter", "s2", "CREATE", {"name": "Gym"}),
    ]
    for ev in events:
        store.append(ev)

    assert store.get_contiguous_high_water_mark("node-B") == 0
    assert store.get_missing_counter_ranges("node-B") == [(1, 1)]
    assert store.get_version_vector() == {"node-B": 0}
    store.close()


def test_chwm_perfect_contiguous():
    store = SQLiteEventStore(":memory:")
    events = [
        Event("node-C", 1, 10.0, "supply", "sup1", "CREATE", {"item": "Blankets", "total_quantity": 50}),
        Event("node-C", 2, 20.0, "supply", "sup2", "CREATE", {"item": "Tents", "total_quantity": 20}),
        Event("node-C", 3, 30.0, "supply", "sup3", "CREATE", {"item": "Water", "total_quantity": 100}),
    ]
    for ev in events:
        store.append(ev)

    assert store.get_contiguous_high_water_mark("node-C") == 3
    assert store.get_missing_counter_ranges("node-C") == []
    assert store.get_all_gaps() == {}
    assert store.get_version_vector() == {"node-C": 3}
    store.close()


def test_get_events_for_counter_ranges():
    store = SQLiteEventStore(":memory:")
    for c in range(1, 11):
        store.append(Event("node-A", c, float(c * 10), "need", f"n{c}", "CREATE", {"item": f"Item-{c}"}))

    # Request ranges (3, 4) and (7, 8)
    requested_ranges = {"node-A": [(3, 4), (7, 8)]}
    matched = store.get_events_for_counter_ranges(requested_ranges)
    counters = [e.counter for e in matched]
    assert counters == [3, 4, 7, 8]
    store.close()


def test_out_of_order_arrival_gap_repair_sync():
    transport = InMemoryTransport()

    node_a = Node("node-A", db_path=":memory:", transport=transport)
    node_b = Node("node-B", db_path=":memory:", transport=transport)

    # Node A produces 5 sequential events (A1..A5)
    events_a = [
        node_a.record_event("need", f"need-{i}", "CREATE", {"item": f"Item-{i}"})
        for i in range(1, 6)
    ]
    assert len(events_a) == 5
    assert node_a.get_version_vector() == {"node-A": 5}

    # Node B manually receives only A1 and A5 out-of-order (simulating packet loss / data mule)
    node_b.store.append(events_a[0])  # A1
    node_b.store.append(events_a[4])  # A5

    # Check Node B's state before sync
    assert node_b.store.get_contiguous_high_water_mark("node-A") == 1
    assert node_b.store.get_missing_counter_ranges("node-A") == [(2, 4)]
    assert node_b.store.get_all_gaps() == {"node-A": [(2, 4)]}
    assert node_b.get_version_vector() == {"node-A": 1}

    # Node B syncs with Node A
    stats = node_b.sync_with("node-A")
    assert stats.success is True
    # Node B should have received missing events (A2, A3, A4, A5)
    assert stats.events_received >= 3

    # Verify that Node B's gaps are now completely healed
    assert node_b.store.get_all_gaps() == {}
    assert node_b.store.get_contiguous_high_water_mark("node-A") == 5
    assert node_b.get_version_vector() == {"node-A": 5}
    assert node_b.store.count() == 5

    node_a.close()
    node_b.close()


def test_query_events_pagination_and_filtering():
    store = SQLiteEventStore(":memory:")
    # Seed 15 events
    for i in range(1, 11):
        store.append(Event("node-A", i, float(i * 10), "need", f"need-{i}", "CREATE", {"item": f"Item {i}"}))
    for i in range(1, 6):
        store.append(Event("node-B", i, float(100 + i * 10), "shelter", f"sh-{i}", "CREATE", {"name": f"Shelter {i}"}))

    assert store.count() == 15

    # Test filtering by entity_type="shelter"
    shelters, total_sh = store.query_events(entity_type="shelter", limit=10, offset=0)
    assert total_sh == 5
    assert len(shelters) == 5
    assert all(e.entity_type == "shelter" for e in shelters)

    # Test filtering by node_id="node-A"
    node_a_events, total_a = store.query_events(node_id="node-A", limit=5, offset=0)
    assert total_a == 10
    assert len(node_a_events) == 5

    # Test pagination with offset
    page2, total_a = store.query_events(node_id="node-A", limit=5, offset=5)
    assert len(page2) == 5
    # Ensure page 1 and page 2 have no overlapping event_ids
    page1_ids = {e.event_id for e in node_a_events}
    page2_ids = {e.event_id for e in page2}
    assert len(page1_ids.intersection(page2_ids)) == 0

    store.close()
