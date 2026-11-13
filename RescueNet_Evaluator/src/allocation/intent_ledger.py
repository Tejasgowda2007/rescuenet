"""
Pillar 2: Intent-First Soft Allocation Ledger.
Solves the double-allocation trap during network splits.

Design:
- Offline nodes write conditional 'Reservation Intentions' rather than irrevocable hard locks.
- Upon reconnection, post-sync collision detection checks if Total Claimed > Total Available.
- If over-claimed, triggers an Inventory Triage Alert on the coordinator dashboard.
- Coordinator overrides / splits inventory to guarantee zero double-allocation with zero lost data.
"""

from __future__ import annotations
from typing import Dict, Any, Optional
from events.event import Event


class IntentLedger:
    """
    Manages soft inventory reservations, post-sync collision detection,
    and coordinator triage resolution.
    """

    @staticmethod
    def init_pool(
        node: Any,
        item_id: str,
        item_name: str,
        total_quantity: int,
        unit: str = "kits",
    ) -> Event:
        """Initialize an inventory pool governed by intent-based soft reservations."""
        return node.record_event(
            entity_type="supply_intent",
            entity_id=item_id,
            operation="INIT_POOL",
            payload={
                "item_name": item_name,
                "total_quantity": total_quantity,
                "unit": unit,
            },
        )

    @staticmethod
    def record_intent(
        node: Any,
        item_id: str,
        quantity: int,
        beneficiary: str = "Emergency Patients",
    ) -> Event:
        """
        Record an offline reservation intention.
        Does not mutate global state; writes an intent to be evaluated upon sync.
        """
        return node.record_event(
            entity_type="supply_intent",
            entity_id=item_id,
            operation="RECORD_INTENT",
            payload={
                "quantity": int(quantity),
                "beneficiary": beneficiary,
                "requested_by": node.node_id,
            },
        )

    @staticmethod
    def resolve_collision(
        node: Any,
        item_id: str,
        approved_allocations: Dict[str, int],
        resolution_notes: str = "Coordinator manual triage split",
    ) -> Event:
        """
        Coordinator resolves an inventory collision by confirming final granted quotas.
        Invariant: sum(approved_allocations.values()) <= total_quantity.
        """
        return node.record_event(
            entity_type="supply_intent",
            entity_id=item_id,
            operation="RESOLVE_COLLISION",
            payload={
                "approved_allocations": approved_allocations,
                "resolution_notes": resolution_notes,
                "resolved_by": node.node_id,
            },
        )
