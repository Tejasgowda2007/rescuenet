"""
Workload Generator for Disaster Simulation.

Generates realistic events:
- Shelters and capacity updates
- Needs and triage resolutions
- Intentional concurrent conflicting person sightings across partitions
- Escrow quota consumption within local limits
- Indivisible scarce item requests and token-holder allocations
"""

from __future__ import annotations
import random
from typing import List, Dict, Any
from sync.node import Node
from allocation.escrow import EscrowManager, InsufficientQuotaError
from allocation.tokens import TokenManager, UnauthorizedAllocationError


class WorkloadGenerator:
    """
    Generates stochastic disaster field actions on simulated nodes.
    """

    NEED_CATEGORIES = ["Water", "Food", "Medical", "Shelter", "Blankets", "Infant Formula"]
    SHELTER_NAMES = ["High School Gym", "Civic Center", "St. Jude Hall", "Memorial Stadium", "Riverfront Church"]
    NAMES_POOL = [
        "Alex Rivera", "Jordan Lee", "Taylor Swift", "Carlos Gomez",
        "Priya Patel", "Marcus Chen", "Fatima Al-Sayed", "Liam O'Connor"
    ]

    @classmethod
    def generate_random_action(
        cls,
        node: Node,
        rng: random.Random,
        active_people: List[str],
        active_supplies: List[str],
        active_scarce_items: List[str],
    ) -> str:
        """
        Pick a random realistic field operation to execute on the node.
        Returns a short descriptive summary of what was logged.
        """
        action_type = rng.choice(["shelter", "need", "person", "supply", "scarce_item"])

        if action_type == "shelter":
            sh_id = f"shelter-{rng.randint(1, 4)}"
            occupancy_change = rng.randint(5, 30)
            node.record_event(
                entity_type="shelter",
                entity_id=sh_id,
                operation="UPDATE",
                payload={"name": rng.choice(cls.SHELTER_NAMES), "occupancy": occupancy_change},
            )
            return f"{node.node_id} updated {sh_id} occupancy to {occupancy_change}"

        elif action_type == "need":
            need_id = f"need-{rng.randint(1, 10)}"
            node.record_event(
                entity_type="need",
                entity_id=need_id,
                operation="CREATE",
                payload={
                    "item": rng.choice(cls.NEED_CATEGORIES),
                    "urgency": rng.choice(["LOW", "MEDIUM", "HIGH", "CRITICAL"]),
                    "location": f"Sector {rng.randint(1, 8)}",
                },
            )
            return f"{node.node_id} logged need {need_id}"

        elif action_type == "person":
            if not active_people:
                pid = f"person-{rng.randint(100, 999)}"
                active_people.append(pid)
            else:
                pid = rng.choice(active_people)

            status = rng.choice(["MISSING", "FOUND_SAFE", "INJURED_IN_TRANSIT", "SHELTERED"])
            location = f"Zone {rng.choice(['North', 'South', 'Delta', 'Highland'])}"
            node.record_event(
                entity_type="person",
                entity_id=pid,
                operation="UPDATE",
                payload={"status": status, "location": location, "name": rng.choice(cls.NAMES_POOL)},
            )
            return f"{node.node_id} recorded {pid} as {status} at {location}"

        elif action_type == "supply" and active_supplies:
            sid = rng.choice(active_supplies)
            state = node.get_state()
            sup_data = state.get("supply", {}).get(sid, {})
            avail = sup_data.get("quotas", {}).get(node.node_id, 0)
            if avail > 0:
                consume_qty = rng.randint(1, min(avail, 5))
                try:
                    EscrowManager.consume(node, sid, consume_qty, f"Field Clinic {node.node_id}")
                    return f"{node.node_id} consumed {consume_qty} of {sid} (quota remaining: {avail - consume_qty})"
                except InsufficientQuotaError:
                    pass
            return f"{node.node_id} inspected {sid}"

        elif action_type == "scarce_item" and active_scarce_items:
            item_id = rng.choice(active_scarce_items)
            state = node.get_state()
            item_data = state.get("scarce_item", {}).get(item_id, {})
            is_holder = item_data.get("token_holder") == node.node_id
            status = item_data.get("status")

            if is_holder and status == "AVAILABLE":
                # Token holder can allocate
                try:
                    TokenManager.confirm_allocation(
                        node, item_id,
                        assigned_to_mission=f"Evacuation Run by {node.node_id}",
                        target_node_id=node.node_id
                    )
                    return f"{node.node_id} (token holder) ALLOCATED {item_id}"
                except UnauthorizedAllocationError:
                    pass
            elif not is_holder:
                # Non-holder issues offline request
                TokenManager.request_allocation(
                    node, item_id,
                    mission_description=f"Emergency Request from {node.node_id}",
                    urgency="HIGH"
                )
                return f"{node.node_id} submitted offline REQUEST for {item_id}"

        return f"{node.node_id} idle standby"

    @classmethod
    def inject_concurrent_conflicts(
        cls,
        nodes: List[Node],
        person_id: str,
        person_name: str,
    ) -> List[str]:
        """
        Explicitly inject conflicting reports for the same person across different nodes.
        Used to test convergence and zero lost updates under severe partition splits.
        """
        statuses = [
            ("MISSING", "Last seen near Bridge Collapse"),
            ("FOUND_SAFE", "Sheltered at Highland Community Church"),
            ("HOSPITALIZED", "Treated for hypothermia at Field Tent 3"),
            ("EVACUATED", "Boarded transport truck #4 heading inland"),
        ]

        summaries = []
        for i, node in enumerate(nodes):
            status, loc = statuses[i % len(statuses)]
            node.record_event(
                entity_type="person",
                entity_id=person_id,
                operation="UPDATE",
                payload={"name": person_name, "status": status, "location": loc},
            )
            summaries.append(f"{node.node_id} reported {person_id} as '{status}' at '{loc}'")

        return summaries
