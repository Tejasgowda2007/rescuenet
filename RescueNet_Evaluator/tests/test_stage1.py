"""
Unit and Integration Tests for Stage 1:
Event Log, SQLite Storage, and Deterministic State Projection.
"""

import os
import random
import pytest
from events.event import Event
from storage.sqlite_store import SQLiteEventStore, EquivocationError
from storage.projector import StateProjector


def test_event_deterministic_id_and_serialization():
    """Verify that event IDs are deterministic and serialization round-trips cleanly."""
    ev1 = Event(
        node_id="volunteer-1",
        counter=1,
        timestamp=1700000000.0,
        entity_type="person",
        entity_id="p-100",
        operation="CREATE",
        payload={"name": "Sarah Connor", "status": "MISSING", "age": 29},
    )

    ev2 = Event(
        node_id="volunteer-1",
        counter=1,
        timestamp=1700000000.0,
        entity_type="person",
        entity_id="p-100",
        operation="CREATE",
        payload={"name": "Sarah Connor", "status": "MISSING", "age": 29},
    )

    # Content addressing: identical attributes must yield identical event_id
    assert ev1.event_id == ev2.event_id
    assert len(ev1.event_id) == 64  # SHA-256 hex string

    # JSON round-trip
    json_str = ev1.to_json()
    reconstructed = Event.from_json(json_str)
    assert reconstructed == ev1
    assert reconstructed.wire_byte_size() > 0


def test_sqlite_append_and_idempotency():
    """Verify append-only semantics and idempotent duplicate handling."""
    store = SQLiteEventStore(":memory:")

    ev = Event(
        node_id="node-A",
        counter=1,
        timestamp=100.0,
        entity_type="shelter",
        entity_id="shelter-north",
        operation="CREATE",
        payload={"name": "North High Gym", "capacity": 150},
    )

    # First insertion should return True (new event)
    assert store.append(ev) is True
    assert store.count() == 1

    # Second insertion of exact same event should return False (no-op, idempotent)
    assert store.append(ev) is False
    assert store.count() == 1

    retrieved = store.get_event(ev.event_id)
    assert retrieved is not None
    assert retrieved.entity_id == "shelter-north"
    assert retrieved.payload["capacity"] == 150

    store.close()


def test_equivocation_detection():
    """
    Verify anti-equivocation invariant:
    A single node cannot issue two different events with the same sequence counter.
    """
    store = SQLiteEventStore(":memory:")

    ev1 = Event(
        node_id="node-A",
        counter=1,
        timestamp=100.0,
        entity_type="supply",
        entity_id="water-bottles",
        operation="CREATE",
        payload={"quantity": 500},
    )
    store.append(ev1)

    # Forked attempt: same node, same counter=1, different payload/entity
    ev_forked = Event(
        node_id="node-A",
        counter=1,
        timestamp=105.0,
        entity_type="supply",
        entity_id="water-bottles",
        operation="CREATE",
        payload={"quantity": 9999},  # conflicting reality
    )

    with pytest.raises(EquivocationError):
        store.append(ev_forked)

    store.close()


def test_version_vector_and_delta_sync():
    """
    Verify version vector calculation and delta extraction for sync:
    get_events_since(peer_vector) must return ONLY events the peer is missing.
    """
    store = SQLiteEventStore(":memory:")

    events_a = [
        Event("node-A", 1, 10.0, "need", "n-1", "CREATE", {"desc": "Blankets"}),
        Event("node-A", 2, 20.0, "need", "n-2", "CREATE", {"desc": "Flashlights"}),
        Event("node-A", 3, 30.0, "need", "n-3", "CREATE", {"desc": "Batteries"}),
    ]
    events_b = [
        Event("node-B", 1, 15.0, "supply", "s-1", "CREATE", {"item": "Cots", "qty": 40}),
        Event("node-B", 2, 25.0, "supply", "s-2", "CREATE", {"item": "Tarps", "qty": 10}),
    ]

    for ev in events_a + events_b:
        store.append(ev)

    # Local version vector should track max counter per node
    vv = store.get_version_vector()
    assert vv == {"node-A": 3, "node-B": 2}

    # Peer has seen node-A up to counter 2, and node-B up to counter 1
    peer_vv = {"node-A": 2, "node-B": 1}
    delta = store.get_events_since(peer_vv)

    # Delta should contain only node-A:3 and node-B:2
    assert len(delta) == 2
    delta_keys = {(e.node_id, e.counter) for e in delta}
    assert delta_keys == {("node-A", 3), ("node-B", 2)}

    store.close()


def test_state_projector_convergence_under_arbitrary_arrival_order():
    """
    Verify that state projection converges to identical state
    regardless of the order events arrive.
    """
    events = [
        Event("node-A", 1, 100.0, "shelter", "sh-1", "CREATE", {"name": "Central Arena", "capacity": 300}),
        Event("node-B", 1, 110.0, "shelter", "sh-1", "UPDATE", {"occupancy": 50}),
        Event("node-A", 2, 120.0, "shelter", "sh-1", "UPDATE", {"occupancy": 75}),
        Event("node-C", 1, 105.0, "person", "p-1", "CREATE", {"name": "John Doe", "status": "MISSING"}),
        Event("node-B", 2, 130.0, "need", "nd-1", "CREATE", {"desc": "Insulin required", "urgency": "CRITICAL"}),
        Event("node-A", 3, 140.0, "need", "nd-1", "RESOLVE", {"resolution_note": "Paramedic dispatched"}),
    ]

    projector = StateProjector()

    # Base projection
    state_original = projector.compute_state(events)

    # Project under 10 different random permutations of the event stream
    for seed in range(10):
        shuffled = list(events)
        random.Random(seed).shuffle(shuffled)
        state_shuffled = projector.compute_state(shuffled)

        assert state_shuffled == state_original, f"State diverged on shuffle seed {seed}"

    # Verify state values
    shelter = state_original["shelter"]["sh-1"]
    assert shelter["name"] == "Central Arena"
    assert shelter["occupancy"] == 75  # Most recent update (timestamp 120 > 110)

    need = state_original["need"]["nd-1"]
    assert need["status"] == "RESOLVED"
    assert need["resolution_note"] == "Paramedic dispatched"


def test_zero_lost_updates_conflict_flagging():
    """
    Requirement 2: Conflicting edits merge with ZERO lost updates (never silently overwrite).
    When two nodes report conflicting statuses for a person, both are recorded.
    """
    projector = StateProjector()

    # Node-A records John Doe missing
    ev1 = Event("node-A", 1, 200.0, "person", "p-99", "CREATE", {
        "name": "Jane Smith", "status": "MISSING", "location": "Sector 4"
    })
    # Node-B concurrently records Jane Smith found at Shelter 2
    ev2 = Event("node-B", 1, 210.0, "person", "p-99", "UPDATE", {
        "status": "FOUND_SAFE", "location": "Shelter 2"
    })

    state = projector.compute_state([ev1, ev2])
    person = state["person"]["p-99"]

    # Conflict must be flagged for triage
    assert len(person["conflicts"]) == 1
    conflict = person["conflicts"][0]
    assert conflict["node_id"] == "node-B"
    assert conflict["conflicting_status"] == "FOUND_SAFE"
    assert conflict["previous_status"] == "MISSING"
    assert person["status"] == "FOUND_SAFE"  # Merged view shows latest, but keeps audit conflict


def test_tombstone_preserves_immutable_audit_log():
    """
    Verify that tombstoning marks entity as deleted in state projection,
    while 100% of the raw events remain preserved in the SQLite database.
    """
    store = SQLiteEventStore(":memory:")
    projector = StateProjector()

    ev_create = Event("node-A", 1, 10.0, "need", "need-77", "CREATE", {"desc": "Tents"})
    ev_delete = Event("node-A", 2, 20.0, "need", "need-77", "TOMBSTONE", {})

    store.append(ev_create)
    store.append(ev_delete)

    # SQLite store still has both events
    assert store.count() == 2
    assert store.get_event(ev_create.event_id) is not None
    assert store.get_event(ev_delete.event_id) is not None

    # State projection marks entity as tombstoned
    state = projector.compute_state(store.get_all_events())
    assert state["need"]["need-77"]["_tombstoned"] is True

    store.close()
