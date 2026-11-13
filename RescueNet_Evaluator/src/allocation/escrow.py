"""
Escrow Quota Allocation for Countable / Divisible Supplies.

Why Double Allocation is Impossible (Not Just Detected):
---------------------------------------------------------
Under the CAP theorem, offline partitions make central locks impossible.
If two partitioned nodes are allowed to independently spend from a shared counter,
an over-allocation is guaranteed when they reconnect.

Instead of a shared counter, we use Escrow Quotas (inspired by Bounded Counter CRDTs):
1. A depot pool of N items is partitioned into explicit non-overlapping allowances:
   Total = Quota(Node_1) + Quota(Node_2) + ... + Quota(Depot)
2. A node can ONLY consume up to its local Quota balance.
3. Offline, a node has strict zero-trust limits: if it runs out of its quota,
   it CANNOT consume more until it physically meets another node and receives a
   quota transfer.
4. Conservation of Supply Invariant:
   sum(active_quotas) + sum(consumed) == total_inventory at all times.
   Because no term can be negative, sum(consumed) can NEVER exceed total_inventory,
   even under arbitrary splits, reordered syncs, or network chaos.
"""

from __future__ import annotations
from typing import Dict, Any, Optional
from events.event import Event


class InsufficientQuotaError(Exception):
    """Raised when an operation attempts to allocate more supplies than available in quota."""
    pass


class EscrowManager:
    """
    Manages local quota validation and emits escrow lifecycle events.
    """

    @staticmethod
    def create_pool(
        node: Any,  # Node instance
        supply_id: str,
        item_name: str,
        total_quantity: int,
        initial_quotas: Dict[str, int],
        unit: str = "units",
    ) -> Event:
        """
        Initialize an escrow pool for a divisible supply (e.g. 100 water crates).
        :param initial_quotas: Mapping of {node_id: allowed_quantity}. Sum must equal total_quantity.
        """
        quota_sum = sum(initial_quotas.values())
        if quota_sum > total_quantity:
            raise ValueError(
                f"Sum of quotas ({quota_sum}) exceeds total supply quantity ({total_quantity})"
            )

        payload = {
            "item_name": item_name,
            "total_quantity": total_quantity,
            "unit": unit,
            "initial_quotas": dict(initial_quotas),
        }

        return node.record_event(
            entity_type="supply",
            entity_id=supply_id,
            operation="INIT_ESCROW",
            payload=payload,
        )

    @staticmethod
    def consume(
        node: Any,  # Node instance
        supply_id: str,
        quantity: int,
        beneficiary: str,
        notes: str = "",
    ) -> Event:
        """
        Consume a quantity of supplies from this node's local escrow allowance.
        Strictly checked against local materialized state before event creation.
        """
        if quantity <= 0:
            raise ValueError("Quantity to consume must be greater than zero")

        state = node.get_state()
        supplies = state.get("supply", {})

        if supply_id not in supplies:
            raise KeyError(f"Supply pool '{supply_id}' does not exist in local state")

        supply_data = supplies[supply_id]
        node_quotas = supply_data.get("quotas", {})
        available = node_quotas.get(node.node_id, 0)

        if available < quantity:
            raise InsufficientQuotaError(
                f"Node '{node.node_id}' cannot allocate {quantity} {supply_data.get('unit', 'units')} "
                f"of '{supply_data.get('item_name')}'. Available quota is only {available}."
            )

        payload = {
            "quantity": quantity,
            "beneficiary": beneficiary,
            "notes": notes,
            "previous_quota": available,
            "new_quota": available - quantity,
        }

        return node.record_event(
            entity_type="supply",
            entity_id=supply_id,
            operation="CONSUME_QUOTA",
            payload=payload,
        )

    @staticmethod
    def transfer_quota(
        from_node: Any,  # Node instance
        to_node_id: str,
        supply_id: str,
        quantity: int,
        reason: str = "",
    ) -> Event:
        """
        Transfer a portion of this node's unused escrow quota to a peer node.
        Used when volunteers meet at a checkpoint and rebalance supplies.
        """
        if quantity <= 0:
            raise ValueError("Transfer quantity must be positive")

        state = from_node.get_state()
        supplies = state.get("supply", {})
        if supply_id not in supplies:
            raise KeyError(f"Supply pool '{supply_id}' does not exist")

        supply_data = supplies[supply_id]
        available = supply_data.get("quotas", {}).get(from_node.node_id, 0)

        if available < quantity:
            raise InsufficientQuotaError(
                f"Cannot transfer {quantity} units. Available quota for '{from_node.node_id}' is {available}."
            )

        payload = {
            "from_node": from_node.node_id,
            "to_node": to_node_id,
            "quantity": quantity,
            "reason": reason,
        }

        return from_node.record_event(
            entity_type="supply",
            entity_id=supply_id,
            operation="TRANSFER_QUOTA",
            payload=payload,
        )
