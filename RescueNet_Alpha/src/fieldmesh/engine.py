"""
FieldMesh Discrete-Event Simulation Engine (SimPy).

Implements realistic packet-level scheduling, transmission airtime, propagation delay,
half-duplex channel contention, PER-based packet drops, acknowledgements,
and multi-hop store-and-forward relay execution.
"""

from __future__ import annotations
import simpy
import random
import time
import threading
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from .terrain import TerrainModel
from .stations import RescueStation
from .topology import TopologyManager
from .packet import Packet, PRIORITY_SOS, PRIORITY_SYNC, PacketFragmentationManager


@dataclass
class PacketTransmissionRecord:
    packet_id: str
    original_msg_id: str
    source_id: str
    destination_id: str
    hop_source: str
    hop_target: str
    msg_type: str
    priority: int
    bytes_count: int
    start_sim_time: float
    end_sim_time: float
    delivered: bool
    dropped_reason: str = ""
    route_taken: List[str] = field(default_factory=list)


class SimulationEngine:
    """
    SimPy-backed discrete-event packet simulation engine for FieldMesh.
    """

    def __init__(
        self,
        terrain: TerrainModel,
        stations: Dict[str, RescueStation],
        topology: TopologyManager,
        seed: int = 42,
    ) -> None:
        self.terrain = terrain
        self.stations = stations
        self.topology = topology
        self.seed = seed
        self.rng = random.Random(seed)

        self.env = simpy.Environment()
        self.frag_mgr = PacketFragmentationManager()

        # Telemetry records
        self.transmission_log: List[PacketTransmissionRecord] = []
        self.total_packets_sent: int = 0
        self.total_packets_delivered: int = 0
        self.total_packets_dropped: int = 0
        self.total_bytes_transferred: int = 0

        # Channel locks for half-duplex transceivers: {frozenset({n1, n2}): simpy.Resource}
        self._channel_resources: Dict[frozenset, simpy.Resource] = {}

        # Packet delivery callbacks: func(packet)
        self.on_packet_delivered_callbacks: List[Callable[[Packet], None]] = []

        # Background runner thread control
        self.is_running = False
        self.is_paused = False
        self.speed_multiplier = 1.0
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    def _get_channel_resource(self, n1: str, n2: str) -> simpy.PriorityResource:
        key = frozenset({n1, n2})
        if key not in self._channel_resources:
            self._channel_resources[key] = simpy.PriorityResource(self.env, capacity=1)
        return self._channel_resources[key]

    def schedule_packet(self, packet: Packet) -> None:
        """
        Inject a new packet into the simulation environment for routing and delivery.
        """
        self.env.process(self._route_and_deliver_process(packet))

    def _route_and_deliver_process(self, packet: Packet):
        """
        SimPy generator process managing multi-hop forwarding from source to destination.
        """
        curr_node_id = packet.source_id
        dest_node_id = packet.destination_id

        # Route discovery
        if dest_node_id == "BROADCAST":
            # Broadcast to all immediate 1-hop neighbors
            neighbors = list(self.topology.graph.neighbors(curr_node_id))
            for nbr in neighbors:
                p_copy = packet.create_forward_copy(curr_node_id, nbr)
                if p_copy:
                    self.env.process(self._single_hop_transmit_process(p_copy, curr_node_id, nbr, final_dest=nbr))
            return

        # Unicast multi-hop route
        route = self.topology.get_route(curr_node_id, dest_node_id)
        if not route or len(route) < 2:
            # Destination partitioned / unreachable!
            self.total_packets_sent += 1
            self.total_packets_dropped += 1
            rec = PacketTransmissionRecord(
                packet_id=packet.packet_id,
                original_msg_id=packet.original_msg_id,
                source_id=packet.source_id,
                destination_id=packet.destination_id,
                hop_source=curr_node_id,
                hop_target=dest_node_id,
                msg_type=packet.msg_type,
                priority=packet.priority,
                bytes_count=packet.wire_byte_size(),
                start_sim_time=self.env.now,
                end_sim_time=self.env.now,
                delivered=False,
                dropped_reason="No viable multi-hop route (Network Partition)",
            )
            self.transmission_log.append(rec)
            return

        # Progress hop-by-hop along route
        yield from self._execute_multi_hop_traversal(packet, route)

    def _execute_multi_hop_traversal(self, packet: Packet, route: List[str]):
        """Traverse route [s, r1, r2, ..., d] hop-by-hop."""
        for hop_idx in range(len(route) - 1):
            h_src = route[hop_idx]
            h_dst = route[hop_idx + 1]

            # Re-verify link at transmission time
            if not self.topology.is_link_connected(h_src, h_dst):
                self.total_packets_sent += 1
                self.total_packets_dropped += 1
                rec = PacketTransmissionRecord(
                    packet_id=packet.packet_id,
                    original_msg_id=packet.original_msg_id,
                    source_id=packet.source_id,
                    destination_id=packet.destination_id,
                    hop_source=h_src,
                    hop_target=h_dst,
                    msg_type=packet.msg_type,
                    priority=packet.priority,
                    bytes_count=packet.wire_byte_size(),
                    start_sim_time=self.env.now,
                    end_sim_time=self.env.now,
                    delivered=False,
                    dropped_reason=f"Link {h_src}->{h_dst} severed during traversal",
                    route_taken=route[:hop_idx + 1],
                )
                self.transmission_log.append(rec)
                return

            # Transmit single hop
            delivered = yield from self._single_hop_transmit_process(
                packet=packet,
                hop_src=h_src,
                hop_dst=h_dst,
                final_dest=route[-1],
            )
            if not delivered:
                # Dropped at this hop
                return

            # Intermediate relay buffering delay
            if h_dst != route[-1]:
                yield self.env.timeout(0.015)  # 15 ms store-and-forward relay processing

        # Successfully delivered to final destination!
        full_payload = self.frag_mgr.receive_fragment(packet)
        if full_payload is not None:
            # Reassembly complete
            reassembled_pkt = Packet(
                packet_id=packet.packet_id,
                source_id=packet.source_id,
                destination_id=packet.destination_id,
                prev_hop=packet.prev_hop,
                next_hop="",
                msg_type=packet.msg_type,
                priority=packet.priority,
                payload=full_payload,
                route_history=route,
            )
            for cb in self.on_packet_delivered_callbacks:
                try:
                    cb(reassembled_pkt)
                except Exception:
                    pass

    def _single_hop_transmit_process(self, packet: Packet, hop_src: str, hop_dst: str, final_dest: str):
        """Simulate single physical radio hop transmission with resource lock and loss chance."""
        link_info = self.topology.get_link_info(hop_src, hop_dst)
        bytes_count = packet.wire_byte_size()
        start_time = self.env.now

        self.total_packets_sent += 1
        self.total_bytes_transferred += bytes_count

        if hop_src in self.stations:
            self.stations[hop_src].tx_packet_count += 1
            self.stations[hop_src].bytes_sent += bytes_count
            self.stations[hop_src].battery.step(0.0005, is_tx=True)

        channel_res = self._get_channel_resource(hop_src, hop_dst)
        with channel_res.request(priority=packet.priority) as req:
            yield req  # Wait for channel access

            # Calculate duration in seconds
            airtime_sec = (link_info["latency_ms"] if link_info else 40.0) / 1000.0
            yield self.env.timeout(airtime_sec)

        # Evaluate packet error probability
        per = link_info["per"] if link_info else 0.05
        # High-priority SOS packets get redundant chirp coding bonus (lower effective loss)
        if packet.priority == PRIORITY_SOS:
            per *= 0.3

        dice_roll = self.rng.random()
        delivered = dice_roll >= per

        end_time = self.env.now

        if delivered:
            if hop_dst in self.stations:
                self.stations[hop_dst].rx_packet_count += 1
                self.stations[hop_dst].bytes_received += bytes_count
                self.stations[hop_dst].battery.step(0.0002, is_tx=False)

            if hop_dst == final_dest:
                self.total_packets_delivered += 1

            rec = PacketTransmissionRecord(
                packet_id=packet.packet_id,
                original_msg_id=packet.original_msg_id,
                source_id=packet.source_id,
                destination_id=final_dest,
                hop_source=hop_src,
                hop_target=hop_dst,
                msg_type=packet.msg_type,
                priority=packet.priority,
                bytes_count=bytes_count,
                start_sim_time=round(start_time, 3),
                end_sim_time=round(end_time, 3),
                delivered=True,
                route_taken=packet.route_history,
            )
            self.transmission_log.append(rec)
            return True
        else:
            self.total_packets_dropped += 1
            if hop_src in self.stations:
                self.stations[hop_src].dropped_packet_count += 1

            rec = PacketTransmissionRecord(
                packet_id=packet.packet_id,
                original_msg_id=packet.original_msg_id,
                source_id=packet.source_id,
                destination_id=final_dest,
                hop_source=hop_src,
                hop_target=hop_dst,
                msg_type=packet.msg_type,
                priority=packet.priority,
                bytes_count=bytes_count,
                start_sim_time=round(start_time, 3),
                end_sim_time=round(end_time, 3),
                delivered=False,
                dropped_reason=f"RF Packet Error (PER={round(per, 2)})",
                route_taken=packet.route_history,
            )
            self.transmission_log.append(rec)
            return False

    def step(self, delta_sim_seconds: float = 1.0) -> None:
        """Advance the simulation clock by delta_sim_seconds."""
        with self._lock:
            target_time = self.env.now + delta_sim_seconds
            try:
                self.env.run(until=target_time)
            except Exception:
                pass

    def start_background_loop(self, tick_interval_sec: float = 0.1) -> None:
        """Run discrete simulation clock continuously in a background daemon thread."""
        if self.is_running:
            return
        self.is_running = True
        self.is_paused = False

        def _worker():
            while self.is_running:
                if not self.is_paused:
                    sim_step = tick_interval_sec * self.speed_multiplier
                    self.step(sim_step)
                time.sleep(tick_interval_sec)

        self._thread = threading.Thread(target=_worker, name="FieldMesh-SimPyEngine", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self.is_running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)

    def pause(self) -> None:
        self.is_paused = True

    def resume(self) -> None:
        self.is_paused = False

    def set_speed(self, multiplier: float) -> None:
        self.speed_multiplier = max(0.1, min(20.0, float(multiplier)))

    def get_metrics_snapshot(self) -> Dict[str, Any]:
        """Telemetry statistics computed directly from actual simulation records."""
        total_p = self.total_packets_sent
        delivered_p = self.total_packets_delivered
        ratio = round((delivered_p / max(1, total_p)) * 100.0, 1)

        recent = self.transmission_log[-50:]
        latencies = [
            (r.end_sim_time - r.start_sim_time) * 1000.0
            for r in recent if r.delivered
        ]
        avg_lat = round(sum(latencies) / len(latencies), 1) if latencies else 0.0

        return {
            "sim_time_sec": round(self.env.now, 2),
            "total_packets_sent": total_p,
            "total_packets_delivered": delivered_p,
            "total_packets_dropped": self.total_packets_dropped,
            "delivery_ratio_pct": ratio,
            "total_wire_bytes": self.total_bytes_transferred,
            "avg_latency_ms": avg_lat,
            "is_running": self.is_running,
            "is_paused": self.is_paused,
            "speed_multiplier": self.speed_multiplier,
        }
