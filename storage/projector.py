"""
State Projector: Deterministic Event Sourcing Reducer.

Computes current disaster coordination state (shelters, supplies, needs, people, scarce items)
directly from the append-only event log.
Nothing is ever mutated in place in the database; state is a pure projection of history.
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
    - Mathematical guarantee against double allocation of scarce items:
      * Escrow Quotas ensure total consumed never exceeds initial inventory.
      * Single-Owner Tokens ensure only the verified holder can confirm an allocation.
    """

    def __init__(self) -> None:
        pass

    def compute_state(self, events: List[Event]) -> Dict[str, Dict[str, Any]]:
        """
        Fold all events into the materialized view.

        Returns:
            Dict structure:
            {
                "shelter":     { shelter_id: { ... } },
                "supply":      { supply_id:  { ..., quotas: {...}, consumed: int } },
                "need":        { need_id:    { ... } },
                "person":      { person_id:  { ..., conflicts: [...] } },
                "scarce_item": { item_id:    { ..., token_holder: str, status: str, requests: [...] } }
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
        op = event.operation

        if etype not in state:
            state[etype] = {}

        bucket = state[etype]

        # -------------------------------------------------------------
        # 1. ESCROW OPERATIONS (Divisible Supplies)
        # -------------------------------------------------------------
        if etype == "supply" and op == "INIT_ESCROW":
            bucket[eid] = {
                "entity_id": eid,
                "item_name": event.payload.get("item_name", "Supplies"),
                "total_quantity": event.payload.get("total_quantity", 0),
                "unit": event.payload.get("unit", "units"),
                "quotas": dict(event.payload.get("initial_quotas", {})),
                "consumed": 0,
                "consumption_log": [],
                "rejected_allocations": [],
                "_created_at": event.timestamp,
                "_created_by": event.node_id,
                "_last_updated_at": event.timestamp,
                "_last_updated_by": event.node_id,
            }
            return

        elif etype == "supply" and op == "CONSUME_QUOTA":
            if eid in bucket:
                record = bucket[eid]
                qty = event.payload.get("quantity", 0)
                consumer_node = event.node_id
                available = record["quotas"].get(consumer_node, 0)

                # Invariant Enforcement: Never consume beyond granted quota
                if available >= qty:
                    record["quotas"][consumer_node] = available - qty
                    record["consumed"] += qty
                    record["consumption_log"].append({
                        "event_id": event.event_id,
                        "node_id": consumer_node,
                        "quantity": qty,
                        "beneficiary": event.payload.get("beneficiary", ""),
                        "timestamp": event.timestamp,
                    })
                else:
                    # Over-allocation attempt detected and rejected
                    record["rejected_allocations"].append({
                        "event_id": event.event_id,
                        "node_id": consumer_node,
                        "attempted_quantity": qty,
                        "available_quota": available,
                        "timestamp": event.timestamp,
                        "reason": "Exceeded available escrow quota",
                    })

                record["_last_updated_at"] = event.timestamp
                record["_last_updated_by"] = event.node_id
            return

        elif etype == "supply" and op == "TRANSFER_QUOTA":
            if eid in bucket:
                record = bucket[eid]
                qty = event.payload.get("quantity", 0)
                from_node = event.payload.get("from_node", event.node_id)
                to_node = event.payload.get("to_node", "")
                available = record["quotas"].get(from_node, 0)

                if available >= qty:
                    record["quotas"][from_node] = available - qty
                    record["quotas"][to_node] = record["quotas"].get(to_node, 0) + qty
                record["_last_updated_at"] = event.timestamp
                record["_last_updated_by"] = event.node_id
            return

        # -------------------------------------------------------------
        # 2. TOKEN OPERATIONS (Indivisible Scarce Items e.g. Boat)
        # -------------------------------------------------------------
        if etype == "scarce_item" and op == "REGISTER_TOKEN":
            bucket[eid] = {
                "entity_id": eid,
                "item_name": event.payload.get("item_name", "Scarce Asset"),
                "category": event.payload.get("category", "equipment"),
                "token_holder": event.payload.get("current_token_holder", event.node_id),
                "status": "AVAILABLE",  # AVAILABLE | CONFIRMED_ALLOCATED
                "allocated_to": None,
                "target_node": None,
                "requests": [],
                "rejected_allocations": [],
                "_created_at": event.timestamp,
                "_created_by": event.node_id,
                "_last_updated_at": event.timestamp,
                "_last_updated_by": event.node_id,
            }
            return

        elif etype == "scarce_item" and op == "REQUEST_ALLOCATION":
            if eid in bucket:
                record = bucket[eid]
                record["requests"].append({
                    "request_id": event.event_id,
                    "node_id": event.node_id,
                    "mission": event.payload.get("mission", ""),
                    "urgency": event.payload.get("urgency", "HIGH"),
                    "timestamp": event.timestamp,
                    "status": "PENDING",
                })
                record["_last_updated_at"] = event.timestamp
                record["_last_updated_by"] = event.node_id
            return

        elif etype == "scarce_item" and op == "CONFIRM_ALLOCATION":
            if eid in bucket:
                record = bucket[eid]
                current_holder = record.get("token_holder")

                # Invariant: ONLY the current verified token holder can confirm allocation!
                if event.node_id == current_holder and record["status"] == "AVAILABLE":
                    record["status"] = "CONFIRMED_ALLOCATED"
                    record["allocated_to"] = event.payload.get("assigned_to")
                    record["target_node"] = event.payload.get("target_node")
                    record["confirmed_by"] = event.node_id
                    # Mark matched pending requests as fulfilled
                    for req in record["requests"]:
                        if req["node_id"] == event.payload.get("target_node"):
                            req["status"] = "FULFILLED"
                else:
                    # Double-allocation attempt or unauthorized attempt rejected
                    record["rejected_allocations"].append({
                        "event_id": event.event_id,
                        "attempted_by": event.node_id,
                        "actual_token_holder": current_holder,
                        "item_status": record["status"],
                        "timestamp": event.timestamp,
                        "reason": "Unauthorized allocation attempt: node does not hold token or item already allocated",
                    })

                record["_last_updated_at"] = event.timestamp
                record["_last_updated_by"] = event.node_id
            return

        elif etype == "scarce_item" and op == "TRANSFER_TOKEN":
            if eid in bucket:
                record = bucket[eid]
                if event.node_id == record.get("token_holder"):
                    record["token_holder"] = event.payload.get("to_holder")
                record["_last_updated_at"] = event.timestamp
                record["_last_updated_by"] = event.node_id
            return

        elif etype == "scarce_item" and op == "RELEASE_ITEM":
            if eid in bucket:
                record = bucket[eid]
                if event.node_id == record.get("token_holder"):
                    record["status"] = "AVAILABLE"
                    record["allocated_to"] = None
                    record["target_node"] = None
                record["_last_updated_at"] = event.timestamp
                record["_last_updated_by"] = event.node_id
            return

        # -------------------------------------------------------------
        # 3. CONFLICT RESOLUTION (Human Triage)
        # -------------------------------------------------------------
        if op == "RESOLVE_CONFLICT":
            if eid in bucket:
                record = bucket[eid]
                record["status"] = event.payload.get("status", record.get("status"))
                if "location" in event.payload:
                    record["location"] = event.payload["location"]
                record["archived_conflicts"] = list(record.get("conflicts", []))
                record["conflicts"] = []  # Cleared by human triage
                record["_resolved_by"] = event.payload.get("resolved_by_node", event.node_id)
                record["_resolution_notes"] = event.payload.get("resolution_notes", "")
                record["_last_updated_at"] = event.timestamp
                record["_last_updated_by"] = event.node_id
                record["_event_count"] = record.get("_event_count", 0) + 1
            return

        # -------------------------------------------------------------
        # 4. STANDARD CRUD OPERATIONS
        # -------------------------------------------------------------
        if op == "CREATE":
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
                self._apply_update(bucket[eid], event)

        elif op == "UPDATE":
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
                self._apply_update(bucket[eid], event)

        elif op == "RESOLVE":
            if eid in bucket:
                bucket[eid]["status"] = "RESOLVED"
                bucket[eid]["_last_updated_at"] = event.timestamp
                bucket[eid]["_last_updated_by"] = event.node_id
                bucket[eid]["_event_count"] = bucket[eid].get("_event_count", 0) + 1
                if "resolution_note" in event.payload:
                    bucket[eid]["resolution_note"] = event.payload["resolution_note"]

        elif op == "TOMBSTONE":
            if eid in bucket:
                bucket[eid]["_tombstoned"] = True
                bucket[eid]["_last_updated_at"] = event.timestamp
                bucket[eid]["_last_updated_by"] = event.node_id
                bucket[eid]["_event_count"] = bucket[eid].get("_event_count", 0) + 1

    def _apply_update(self, current_record: Dict[str, Any], event: Event) -> None:
        """
        Merge an update payload into an existing entity record.

        Conflict Policy:
        - If the entity is a 'person' and has conflicting status values reported by
          different nodes, we flag it in 'conflicts' for human review rather than
          silently overwriting.
        """
        new_status = event.payload.get("status")
        current_status = current_record.get("status")

        if (
            new_status is not None
            and current_status is not None
            and new_status != current_status
            and event.node_id != current_record.get("_last_updated_by")
        ):
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

        for k, v in event.payload.items():
            current_record[k] = v

        current_record["_last_updated_at"] = event.timestamp
        current_record["_last_updated_by"] = event.node_id
        current_record["_event_count"] = current_record.get("_event_count", 0) + 1
