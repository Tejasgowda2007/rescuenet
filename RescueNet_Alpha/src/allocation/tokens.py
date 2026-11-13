"""
Single-Owner Token Management for Indivisible Scarce Items (e.g. Rescue Boat, Generator).

Why Double Allocation is Impossible (Not Just Detected):
---------------------------------------------------------
Indivisible items (like a single rescue boat) cannot be partitioned into fractional quotas.
If two disconnected volunteers could both mark the boat as 'ALLOCATED', two rescue teams
would be promised the same single physical asset in flooded areas.

Our Protocol:
1. Single-Owner Token: Exactly one node holds the cryptographic possession token for
   the scarce item at any given moment.
2. Offline Claims are 'REQUESTED' Only: Any node without the token can only submit an
   offline claim (`status='REQUESTED'`). It CANNOT confirm the allocation.
3. Confirmed Allocation Requires Token: Only the current token holder can transition
   an item from 'AVAILABLE' to 'CONFIRMED_ALLOCATED'.
4. Token Transfer: The token holder can hand off custody to another node via an explicit
   handshake event (`TRANSFER_TOKEN`).
5. Convergence Guarantee:
   Because the authorization to allocate is a non-duplicable token that travels along a
   single causal chain, it is mathematically impossible for two confirmed allocations
   to exist concurrently.
"""

from __future__ import annotations
from typing import Dict, Any, Optional
from events.event import Event


class UnauthorizedAllocationError(Exception):
    """Raised when a node without token custody attempts a confirmed allocation."""
    pass


class TokenManager:
    """
    Manages token issuance, offline requests, and confirmed allocations for scarce assets.
    """

    @staticmethod
    def register_item(
        node: Any,  # Node instance
        item_id: str,
        item_name: str,
        initial_holder_id: str,
        location: str = "",
        category: str = "equipment",
    ) -> Event:
        """
        Register a new indivisible scarce item and assign the genesis token holder.
        """
        payload = {
            "item_name": item_name,
            "category": category,
            "current_token_holder": initial_holder_id,
            "initial_holder": initial_holder_id,
            "location": location,
            "status": "AVAILABLE",  # AVAILABLE | CONFIRMED_ALLOCATED
        }

        return node.record_event(
            entity_type="scarce_item",
            entity_id=item_id,
            operation="REGISTER_TOKEN",
            payload=payload,
        )

    @staticmethod
    def request_allocation(
        node: Any,  # Node instance
        item_id: str,
        mission_description: str,
        urgency: str = "HIGH",
    ) -> Event:
        """
        Submit an offline allocation claim.
        Design Decision:
        This event sets status='REQUESTED', NOT confirmed.
        The volunteer knows this is pending confirmation until they sync with the token holder.
        """
        payload = {
            "requested_by": node.node_id,
            "mission": mission_description,
            "urgency": urgency,
            "request_status": "PENDING",
        }

        return node.record_event(
            entity_type="scarce_item",
            entity_id=item_id,
            operation="REQUEST_ALLOCATION",
            payload=payload,
        )

    @staticmethod
    def confirm_allocation(
        node: Any,  # Node instance
        item_id: str,
        assigned_to_mission: str,
        target_node_id: str,
    ) -> Event:
        """
        Confirm allocation of the scarce item.
        Strictly requires that this node is the verified current token holder!
        """
        state = node.get_state()
        items = state.get("scarce_item", {})

        if item_id not in items:
            raise KeyError(f"Scarce item '{item_id}' not found in local state")

        item_data = items[item_id]
        current_holder = item_data.get("token_holder")

        if current_holder != node.node_id:
            raise UnauthorizedAllocationError(
                f"Node '{node.node_id}' cannot confirm allocation of '{item_data.get('item_name')}'. "
                f"Possession token is currently held by '{current_holder}'. "
                f"Offline claims must remain 'REQUESTED' until synced with the token holder."
            )

        if item_data.get("status") == "CONFIRMED_ALLOCATED":
            raise UnauthorizedAllocationError(
                f"Item '{item_data.get('item_name')}' is already allocated to "
                f"'{item_data.get('allocated_to')}'."
            )

        payload = {
            "confirmed_by": node.node_id,
            "target_node": target_node_id,
            "assigned_to": assigned_to_mission,
            "status": "CONFIRMED_ALLOCATED",
        }

        return node.record_event(
            entity_type="scarce_item",
            entity_id=item_id,
            operation="CONFIRM_ALLOCATION",
            payload=payload,
        )

    @staticmethod
    def transfer_token(
        node: Any,  # Node instance
        item_id: str,
        new_holder_id: str,
        reason: str = "",
    ) -> Event:
        """
        Hand off the single-owner possession token to a peer device.
        """
        state = node.get_state()
        items = state.get("scarce_item", {})
        if item_id not in items:
            raise KeyError(f"Scarce item '{item_id}' not found")

        item_data = items[item_id]
        if item_data.get("token_holder") != node.node_id:
            raise UnauthorizedAllocationError(
                f"Node '{node.node_id}' cannot transfer token: currently held by '{item_data.get('token_holder')}'"
            )

        payload = {
            "from_holder": node.node_id,
            "to_holder": new_holder_id,
            "reason": reason,
        }

        return node.record_event(
            entity_type="scarce_item",
            entity_id=item_id,
            operation="TRANSFER_TOKEN",
            payload=payload,
        )

    @staticmethod
    def release_item(
        node: Any,  # Node instance
        item_id: str,
        notes: str = "",
    ) -> Event:
        """
        Release a previously allocated item back to 'AVAILABLE' status.
        Must be done by the token holder.
        """
        state = node.get_state()
        items = state.get("scarce_item", {})
        item_data = items.get(item_id, {})

        if item_data.get("token_holder") != node.node_id:
            raise UnauthorizedAllocationError("Only the current token holder can release the item")

        payload = {
            "released_by": node.node_id,
            "notes": notes,
            "status": "AVAILABLE",
        }

        return node.record_event(
            entity_type="scarce_item",
            entity_id=item_id,
            operation="RELEASE_ITEM",
            payload=payload,
        )
