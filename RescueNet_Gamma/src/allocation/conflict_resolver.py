"""
Conflict Resolution Manager: Human-in-the-loop triage for conflicting reports.

Design Decision:
Requirement 2 specifies: Conflicting edits merge with ZERO lost updates (never silently overwrite).
When volunteers during a disaster report differing observations for the same person
(e.g., Volunteer Alpha notes 'MISSING at River Road', Volunteer Beta notes 'FOUND at Clinic'),
the system holds both in a conflict ledger.
A human operator can review the audit trail and issue an authoritative RESOLVE_CONFLICT event.
"""

from __future__ import annotations
from typing import Dict, Any, List, Optional
from events.event import Event


class ConflictResolver:
    """
    Handles resolution of conflicting records without losing historical context.
    """

    @staticmethod
    def resolve_person_conflict(
        node: Any,  # Node instance
        person_id: str,
        verified_status: str,
        verified_location: str,
        resolution_notes: str,
    ) -> Event:
        """
        Record a human-triage resolution for a conflicted person record.
        """
        state = node.get_state()
        people = state.get("person", {})

        if person_id not in people:
            raise KeyError(f"Person '{person_id}' not found in local state")

        person = people[person_id]
        active_conflicts = person.get("conflicts", [])

        payload = {
            "status": verified_status,
            "location": verified_location,
            "resolution_notes": resolution_notes,
            "resolved_by_node": node.node_id,
            "archived_conflicts": list(active_conflicts),
        }

        return node.record_event(
            entity_type="person",
            entity_id=person_id,
            operation="RESOLVE_CONFLICT",
            payload=payload,
        )
