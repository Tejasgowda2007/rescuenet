"""
RescueNet Multi-Node Manager.

Coordinates multiple independent RescueNet nodes (Alpha, Beta, Gamma),
providing unified operations, telemetry aggregation, topology management,
and live operational controls for the backend API and frontend dashboard.
"""

from __future__ import annotations
import os
import time
from typing import Dict, Any, List, Optional
from events.event import Event
from sync.node import Node
from transport.in_memory import InMemoryTransport
from transport.base import Transport
from allocation.escrow import EscrowManager
from allocation.tokens import TokenManager
from allocation.conflict_resolver import ConflictResolver


class MultiNodeManager:
    """
    Manages a cluster of RescueNet nodes for disaster mesh operations.
    """

    def __init__(
        self,
        transport: Optional[Transport] = None,
        auto_start_gossip: bool = True,
        gossip_interval: float = 2.0,
    ) -> None:
        self.transport = transport if transport is not None else InMemoryTransport()
        self.auto_start_gossip = auto_start_gossip
        self.gossip_interval = gossip_interval
        self.nodes: Dict[str, Node] = {}
        self.created_at = time.time()

    def add_node(
        self,
        node_id: str,
        db_path: str = ":memory:",
        keyring: Optional[Any] = None,
        strict_mode: bool = False,
    ) -> Node:
        """Instantiate and register an independent node in the cluster."""
        if node_id in self.nodes:
            return self.nodes[node_id]

        node = Node(
            node_id=node_id,
            db_path=db_path,
            transport=self.transport,
            keyring=keyring,
            strict_mode=strict_mode,
        )
        self.nodes[node_id] = node

        # Connect peer mesh links if InMemoryTransport
        if isinstance(self.transport, InMemoryTransport):
            for existing_id in self.nodes.keys():
                if existing_id != node_id:
                    self.transport.heal_link(node_id, existing_id)

        # Launch background gossip daemon if enabled
        if self.auto_start_gossip:
            other_peers = [nid for nid in self.nodes.keys() if nid != node_id]
            node.start_gossip(interval_sec=self.gossip_interval, peers=other_peers)
            # Update other nodes to know about this new peer
            for nid, other_node in self.nodes.items():
                if nid != node_id and other_node.gossip_daemon:
                    other_node.gossip_daemon.add_peer(node_id)

        return node

    def get_node(self, node_id: str) -> Optional[Node]:
        """Fetch node instance by ID."""
        return self.nodes.get(node_id)

    def list_nodes(self) -> List[Dict[str, Any]]:
        """Return status and version vectors for all nodes in cluster."""
        result = []
        for nid, node in self.nodes.items():
            gaps = node.store.get_all_gaps()
            result.append({
                "node_id": nid,
                "events_count": node.store.count(),
                "version_vector": node.get_version_vector(),
                "max_version_vector": node.store.get_max_version_vector(),
                "gaps": gaps,
                "has_gaps": len(gaps) > 0,
                "peer_health": node.get_peer_health(),
                "strict_mode": node.strict_mode,
                "keyring_active": node.keyring is not None,
            })
        return result

    # ------------------------------------------------------------------
    # DOMAIN ACTIONS: INCIDENTS
    # ------------------------------------------------------------------

    def create_incident(
        self,
        node_id: str,
        incident_id: str,
        title: str,
        severity: str = "HIGH",  # CRITICAL, HIGH, MEDIUM, LOW
        location: str = "",
        description: str = "",
        assigned_teams: Optional[List[str]] = None,
    ) -> Event:
        node = self.nodes[node_id]
        payload = {
            "title": title,
            "severity": severity.upper(),
            "location": location,
            "description": description,
            "status": "OPEN",
            "assigned_teams": assigned_teams or [],
        }
        return node.record_event("incident", incident_id, "CREATE", payload)

    def assign_team_to_incident(
        self,
        node_id: str,
        incident_id: str,
        team_name: str,
    ) -> Event:
        node = self.nodes[node_id]
        return node.record_event("incident", incident_id, "ASSIGN_TEAM", {"team": team_name})

    def close_incident(
        self,
        node_id: str,
        incident_id: str,
        notes: str = "",
    ) -> Event:
        node = self.nodes[node_id]
        return node.record_event("incident", incident_id, "CLOSE_INCIDENT", {"resolution_notes": notes})

    # ------------------------------------------------------------------
    # DOMAIN ACTIONS: VICTIMS & MEDICAL TRIAGE
    # ------------------------------------------------------------------

    def register_victim(
        self,
        node_id: str,
        victim_id: str,
        name: str,
        triage_category: str = "YELLOW",  # RED (Immediate), YELLOW (Delayed), GREEN (Minor), BLACK (Expectant)
        status: str = "INJURED",  # FOUND, INJURED, CRITICAL, MISSING, DECEASED
        medical_needs: str = "",
        location: str = "",
        contact_info: str = "",
    ) -> Event:
        node = self.nodes[node_id]
        payload = {
            "name": name,
            "triage_category": triage_category.upper(),
            "status": status.upper(),
            "medical_needs": medical_needs,
            "location": location,
            "contact_info": contact_info,
        }
        return node.record_event("victim", victim_id, "CREATE", payload)

    def update_victim_triage(
        self,
        node_id: str,
        victim_id: str,
        triage_category: Optional[str] = None,
        status: Optional[str] = None,
        location: Optional[str] = None,
        medical_needs: Optional[str] = None,
    ) -> Event:
        node = self.nodes[node_id]
        payload: Dict[str, Any] = {}
        if triage_category:
            payload["triage_category"] = triage_category.upper()
        if status:
            payload["status"] = status.upper()
        if location:
            payload["location"] = location
        if medical_needs:
            payload["medical_needs"] = medical_needs
        return node.record_event("victim", victim_id, "UPDATE_TRIAGE", payload)

    # ------------------------------------------------------------------
    # DOMAIN ACTIONS: SHELTERS
    # ------------------------------------------------------------------

    def create_shelter(
        self,
        node_id: str,
        shelter_id: str,
        name: str,
        capacity: int,
        location: str = "",
    ) -> Event:
        node = self.nodes[node_id]
        payload = {
            "name": name,
            "capacity": capacity,
            "occupancy": 0,
            "location": location,
            "status": "OPEN",
        }
        return node.record_event("shelter", shelter_id, "CREATE", payload)

    def update_shelter_occupancy(
        self,
        node_id: str,
        shelter_id: str,
        occupancy: int,
    ) -> Event:
        node = self.nodes[node_id]
        return node.record_event("shelter", shelter_id, "UPDATE", {"occupancy": occupancy})

    # ------------------------------------------------------------------
    # DOMAIN ACTIONS: RESOURCES & ESCROW QUOTAS
    # ------------------------------------------------------------------

    def create_supply_pool(
        self,
        node_id: str,
        supply_id: str,
        item_name: str,
        total_quantity: int,
        initial_quotas: Dict[str, int],
        unit: str = "units",
    ) -> Event:
        node = self.nodes[node_id]
        return EscrowManager.create_pool(
            node=node,
            supply_id=supply_id,
            item_name=item_name,
            total_quantity=total_quantity,
            initial_quotas=initial_quotas,
            unit=unit,
        )

    def consume_supply(
        self,
        node_id: str,
        supply_id: str,
        quantity: int,
        beneficiary: str,
        notes: str = "",
    ) -> Event:
        node = self.nodes[node_id]
        return EscrowManager.consume(
            node=node,
            supply_id=supply_id,
            quantity=quantity,
            beneficiary=beneficiary,
            notes=notes,
        )

    def transfer_supply_quota(
        self,
        from_node_id: str,
        to_node_id: str,
        supply_id: str,
        quantity: int,
    ) -> Event:
        node = self.nodes[from_node_id]
        return EscrowManager.transfer_quota(
            from_node=node,
            supply_id=supply_id,
            to_node_id=to_node_id,
            quantity=quantity,
        )

    # ------------------------------------------------------------------
    # DOMAIN ACTIONS: SCARCE ITEM TOKENS
    # ------------------------------------------------------------------

    def register_scarce_token(
        self,
        node_id: str,
        item_id: str,
        item_name: str,
        initial_holder_id: str,
        category: str = "equipment",
    ) -> Event:
        node = self.nodes[node_id]
        return TokenManager.register_item(
            node=node,
            item_id=item_id,
            item_name=item_name,
            initial_holder_id=initial_holder_id,
            category=category,
        )

    def request_scarce_token(
        self,
        node_id: str,
        item_id: str,
        mission: str,
        urgency: str = "HIGH",
    ) -> Event:
        node = self.nodes[node_id]
        return TokenManager.request_allocation(
            node=node,
            item_id=item_id,
            mission_description=mission,
            urgency=urgency,
        )

    def confirm_scarce_token(
        self,
        node_id: str,
        item_id: str,
        target_node_id: str,
        mission: str,
    ) -> Event:
        node = self.nodes[node_id]
        return TokenManager.confirm_allocation(
            node=node,
            item_id=item_id,
            assigned_to_mission=mission,
            target_node_id=target_node_id,
        )

    def transfer_token_custody(
        self,
        from_node_id: str,
        item_id: str,
        to_node_id: str,
    ) -> Event:
        node = self.nodes[from_node_id]
        return TokenManager.transfer_token(
            node=node,
            item_id=item_id,
            to_node_id=to_node_id,
        )

    # ------------------------------------------------------------------
    # TOPOLOGY & SYNC CONTROLS
    # ------------------------------------------------------------------

    def sync_pair(self, node_a_id: str, node_b_id: str) -> SyncStats:
        """Force immediate anti-entropy sync between two nodes."""
        node_a = self.nodes[node_a_id]
        return node_a.sync_with(node_b_id)

    def sync_all(self) -> Dict[str, List[SyncStats]]:
        """Trigger sync between all pairs of nodes."""
        results: Dict[str, List[SyncStats]] = {}
        for nid, node in self.nodes.items():
            results[nid] = []
            for other_id in self.nodes.keys():
                if other_id != nid:
                    stats = node.sync_with(other_id)
                    results[nid].append(stats)
        return results

    def get_topology(self) -> Dict[str, Any]:
        """Export active graph topology and link states."""
        nodes_list = list(self.nodes.keys())
        edges = []
        is_in_memory = isinstance(self.transport, InMemoryTransport)

        for i, a in enumerate(nodes_list):
            for b in nodes_list[i + 1:]:
                is_connected = True
                if is_in_memory:
                    is_connected = not self.transport.is_partitioned(a, b)
                edges.append({
                    "source": a,
                    "target": b,
                    "connected": is_connected,
                })

        return {
            "nodes": nodes_list,
            "edges": edges,
        }

    def close(self) -> None:
        """Cleanly shutdown all nodes and background daemons."""
        for node in self.nodes.values():
            node.close()
        self.nodes.clear()
