"""
State Projector: Deterministic Event Sourcing Reducer.

Computes current disaster coordination state (shelters, supplies, needs, people)
directly from the append-only event log.
Nothing is ever overwritten in the database; state is a pure projection of history.
"""

from __future__ import annotations
from typing import Dict, Any, List, Optional
from events.event import Event


class StateProjector:
    """
    Folds an append-only sequence of Events into the current disaster coordination state.

    Design Decision:
    - Pure functional reduction: State = fold(events, initial_state).
    - Determinism guarantee: By ordering events canonically (timestamp, node_id, counter),
      any two devices with identical event sets produce byte-for-byte identical state.
    - Zero lost updates: Conflicting reports (e.g. "Person Found" vs "Person Missing"
      reported concurrently by different volunteers) are preserved in a 'conflicts'
      registry rather than silently overwriting.
    """

    def __init__(self) -> None:
        pass

    def compute_state(self, events: List[Event]) -> Dict[str, Dict[str, Any]]:
        """
        Fold all events into the materialized view.

        Returns:
            Dict structure:
            {
                "shelter": { shelter_id: { ...fields, _meta: { ... } } },
                "supply":  { supply_id:  { ...fields, _meta: { ... } } },
                "need":    { need_id:    { ...fields, _meta: { ... } } },
                "person":  { person_id:  { ...fields, _meta: { ... }, conflicts: [...] } },
                "scarce_item": { item_id: { ...fields } }
            }
        """
        # Step 1: Ensure deterministic canonical replay order
        canonical_events = sorted(
            events,
            key=lambda e: (e.timestamp, e.node_id, e.counter)
        )

        # Step 2: Initialize empty state buckets per entity type
        state: Dict[str, Dict[str, Any]] = {
            "shelter": {},
            "supply": {},
            "need": {},
            "person": {},
            "scarce_item": {},
        }

        # Step 3: Apply each event in order
        for event in canonical_events:
            self._apply_event(state, event)

        return state

    def _apply_event(self, state: Dict[str, Dict[str, Any]], event: Event) -> None:
        """Apply a single event to the mutable state accumulator."""
        etype = event.entity_type
        eid = event.entity_id

        if etype not in state:
            state[etype] = {}

        bucket = state[etype]

        if event.operation == "CREATE":
            if eid not in bucket:
                bucket[eid] = {
                    **event.payload,
                    "entity_id": eid,
                    "_created_at": event.timestamp,
                    "_created_by": event.node_id,
                    "_last_updated_at": event.timestamp,
                    "_last_updated_by": event.node_id,
                    "_event_count": 1,
                    "_tombstoned": False,
                    "conflicts": [],
                }
            else:
                # Concurrent CREATE or redundant CREATE: merge payload safely
                self._apply_update(bucket[eid], event)

        elif event.operation == "UPDATE":
            if eid not in bucket:
                # Event arrived out-of-order or before explicit CREATE: synthesize entity
                bucket[eid] = {
                    **event.payload,
                    "entity_id": eid,
                    "_created_at": event.timestamp,
                    "_created_by": event.node_id,
                    "_last_updated_at": event.timestamp,
                    "_last_updated_by": event.node_id,
                    "_event_count": 1,
                    "_tombstoned": False,
                    "conflicts": [],
                }
            else:
                self._apply_update(bucket[eid], event)

        elif event.operation == "RESOLVE":
            if eid in bucket:
                bucket[eid]["status"] = "RESOLVED"
                bucket[eid]["_last_updated_at"] = event.timestamp
                bucket[eid]["_last_updated_by"] = event.node_id
                bucket[eid]["_event_count"] += 1
                if "resolution_note" in event.payload:
                    bucket[eid]["resolution_note"] = event.payload["resolution_note"]

        elif event.operation == "TOMBSTONE":
            if eid in bucket:
                bucket[eid]["_tombstoned"] = True
                bucket[eid]["_last_updated_at"] = event.timestamp
                bucket[eid]["_last_updated_by"] = event.node_id
                bucket[eid]["_event_count"] += 1

    def _apply_update(self, current_record: Dict[str, Any], event: Event) -> None:
        """
        Merge an update payload into an existing entity record.

        Conflict Policy:
        - If the entity is a 'person' and has conflicting status values reported by
          different nodes within a short window, or without causal relationship,
          we flag it in 'conflicts' for human triage instead of silently overwriting.
        - For numerical values like shelter capacity or supply levels, we accept the
          later canonical update while keeping the audit trail.
        """
        # Conflict detection for sensitive status changes (e.g. Person: FOUND vs MISSING)
        new_status = event.payload.get("status")
        current_status = current_record.get("status")

        if (
            new_status is not None
            and current_status is not None
            and new_status != current_status
            and event.node_id != current_record.get("_last_updated_by")
        ):
            # Design Decision: Preserve both conflicting reports for human review (Requirement 2)
            conflict_entry = {
                "event_id": event.event_id,
                "node_id": event.node_id,
                "timestamp": event.timestamp,
                "conflicting_status": new_status,
                "previous_status": current_status,
                "reason": "Concurrent or alternate status reported from different node",
            }
            if "conflicts" not in current_record:
                current_record["conflicts"] = []
            current_record["conflicts"].append(conflict_entry)

        # Merge new attributes into the record
        for k, v in event.payload.items():
            current_record[k] = v

        current_record["_last_updated_at"] = event.timestamp
        current_record["_last_updated_by"] = event.node_id
        current_record["_event_count"] = current_record.get("_event_count", 0) + 1
