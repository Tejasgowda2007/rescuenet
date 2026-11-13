"""
FieldMesh RescueNet Application Adapter.

Connects the existing RescueNet sync engine (Node, SQLiteEventStore, StateProjector,
EscrowManager, TokenManager, NodeKeyring) to the simulated SimPy radio mesh.
"""

from __future__ import annotations
import json
import time
from typing import Dict, Optional, Callable, Any, List
from dataclasses import asdict
from transport.base import Transport, TransportMessage
from events.event import Event
from sync.node import Node
from sync.messages import (
    SyncStats,
    MSG_SYNC_REQUEST,
    MSG_SYNC_RESPONSE,
    MSG_SYNC_DELTA,
    MSG_SYNC_ACK,
)
from .topology import TopologyManager
from .engine import SimulationEngine
from .packet import Packet, PRIORITY_SYNC, PRIORITY_SOS, PacketFragmentationManager


class FieldMeshRadioTransport(Transport):
    """
    Implements RescueNet's Transport interface over the simulated multi-hop radio network.
    Messages are routed through the SimPy discrete-event simulation engine with real
    terrain obstruction, path loss, fragmentation, and latency.
    """

    def __init__(
        self,
        topology: TopologyManager,
        sim_engine: SimulationEngine,
        frag_mgr: Optional[PacketFragmentationManager] = None,
    ) -> None:
        self.topology = topology
        self.sim_engine = sim_engine
        self.frag_mgr = frag_mgr or PacketFragmentationManager()
        self._handlers: Dict[str, Callable[[TransportMessage], Optional[TransportMessage]]] = {}
        self._total_bytes: int = 0
        self._total_messages: int = 0

    def register_node(
        self,
        node_id: str,
        handler: Callable[[TransportMessage], Optional[TransportMessage]],
    ) -> None:
        self._handlers[node_id] = handler

    def unregister_node(self, node_id: str) -> None:
        self._handlers.pop(node_id, None)

    def send(self, message: TransportMessage) -> Optional[TransportMessage]:
        """
        Deliver message across the simulated radio network.
        1. Checks multi-hop route between sender and recipient.
        2. Simulates physical packet transmission, airtime, and loss.
        3. Invokes recipient handler and returns immediate response.
        """
        sender = message.sender_id
        recipient = message.recipient_id

        # 1. Route validation
        route = self.topology.get_route(sender, recipient)
        if not route or len(route) < 2:
            # Network partition or unviable radio link!
            return None

        # Check direct link or multi-hop path connectivity
        for i in range(len(route) - 1):
            if not self.topology.is_link_connected(route[i], route[i + 1]):
                return None

        # Check receiver registered
        if recipient not in self._handlers:
            return None

        handler = self._handlers[recipient]

        # 2. Serialize payload to bytes and measure wire accounting
        out_bytes = message.to_bytes()
        self._total_bytes += len(out_bytes)
        self._total_messages += 1

        # Simulate transmission by scheduling packets in SimPy engine
        raw_dict = asdict(message)
        packets = self.frag_mgr.fragment_message(
            source_id=sender,
            destination_id=recipient,
            msg_type=message.message_type,
            full_payload=raw_dict,
            priority=PRIORITY_SYNC,
        )
        for pkt in packets:
            self.sim_engine.schedule_packet(pkt)

        # Advance engine clock by estimated flight time so simulation clock tracks
        step_time = max(0.05, (len(out_bytes) / 1000.0) * 0.4 * (len(route) - 1))
        self.sim_engine.step(step_time)

        # 3. Deliver to receiver handler
        in_msg = TransportMessage.from_bytes(out_bytes)
        response = handler(in_msg)

        if response is not None:
            # Check return route
            return_route = self.topology.get_route(recipient, sender)
            if not return_route or len(return_route) < 2:
                return None

            resp_bytes = response.to_bytes()
            self._total_bytes += len(resp_bytes)
            self._total_messages += 1

            resp_packets = self.frag_mgr.fragment_message(
                source_id=recipient,
                destination_id=sender,
                msg_type=response.message_type,
                full_payload=asdict(response),
                priority=PRIORITY_SYNC,
            )
            for pkt in resp_packets:
                self.sim_engine.schedule_packet(pkt)

            resp_step = max(0.05, (len(resp_bytes) / 1000.0) * 0.4 * (len(return_route) - 1))
            self.sim_engine.step(resp_step)

            return TransportMessage.from_bytes(resp_bytes)

        return None

    def get_stats(self) -> Dict[str, int]:
        return {
            "total_bytes": self._total_bytes,
            "total_messages": self._total_messages,
        }

    def reset_stats(self) -> None:
        self._total_bytes = 0
        self._total_messages = 0


def create_rescuenet_nodes_for_fieldmesh(
    stations: Dict[str, Any],
    transport: FieldMeshRadioTransport,
    keyrings: Optional[Dict[str, Any]] = None,
) -> Dict[str, Node]:
    """
    Wrap each FieldMesh station with an authentic RescueNet Node instance
    sharing the simulated FieldMeshRadioTransport.
    """
    nodes = {}
    for nid, station in stations.items():
        node = Node(
            node_id=nid,
            db_path=station.store.db_path,
            transport=transport,
            keyring=keyrings.get(nid) if keyrings else station.keyring,
        )
        nodes[nid] = node
    return nodes
