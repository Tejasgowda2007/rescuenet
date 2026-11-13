"""
FieldMesh Network Topology & Routing Graph Engine.

Maintains a dynamic NetworkX graph of all rescue stations and radio links.
Provides:
- Cost-aware multi-hop Dijkstra route calculation.
- Dynamic route recovery when links or relay towers fail.
- Connected component partition detection.
- Per-link status updates (ACTIVE, DEGRADED, BLOCKED, CUT).
"""

from __future__ import annotations
import networkx as nx
from typing import Dict, List, Tuple, Any, Optional
from .terrain import TerrainModel
from .radio import RadioPropagationModel, RadioLinkAssessment, RadioProfile, LORA_DEFAULT_PROFILE, DIRECTIONAL_P2P_PROFILE
from .stations import RescueStation


class TopologyManager:
    """
    Manages the dynamic multi-hop radio topology graph connecting disaster stations.
    """

    def __init__(self, terrain: TerrainModel, stations: Dict[str, RescueStation]) -> None:
        self.terrain = terrain
        self.stations = stations
        self.graph = nx.Graph()
        # Manually forced link cuts / overrides: set of frozenset({node_a, node_b})
        self._manual_cuts: set = set()
        # Edge assessment cache: {(n1, n2): RadioLinkAssessment}
        self.link_assessments: Dict[Tuple[str, str], RadioLinkAssessment] = {}

        self.recompute_all_links()

    def recompute_all_links(self, rain_rate_mm_h: float = 0.0) -> None:
        """
        Evaluate physical-layer radio propagation across all station pairs
        and construct the NetworkX routing graph.
        """
        self.graph.clear()
        node_ids = list(self.stations.keys())

        # Add active stations as graph vertices
        for nid in node_ids:
            stn = self.stations[nid]
            self.graph.add_node(
                nid,
                name=stn.name,
                role=stn.role,
                status=stn.status,
                coords=(stn.x_km, stn.y_km),
                elevation_m=stn.elevation_m,
            )

        self.link_assessments.clear()

        # Evaluate all pair combinations
        for i in range(len(node_ids)):
            for j in range(i + 1, len(node_ids)):
                n1, n2 = node_ids[i], node_ids[j]
                s1, s2 = self.stations[n1], self.stations[n2]

                # Check if both nodes are operational
                nodes_alive = (s1.status in ("ONLINE", "DEGRADED")) and (s2.status in ("ONLINE", "DEGRADED"))

                # Multi-band radio evaluation: prefer high-speed directional P2P microwave if available and viable,
                # fall back to robust sub-GHz LoRa (866 MHz) when microwave is blocked by foliage or attenuation.
                candidates = []
                if s1.has_directional_p2p and s2.has_directional_p2p:
                    candidates.append(DIRECTIONAL_P2P_PROFILE)
                candidates.append(LORA_DEFAULT_PROFILE)

                best_assessment = None
                for prof in candidates:
                    los = self.terrain.check_line_of_sight(
                        tx_pos=(s1.x_km, s1.y_km),
                        rx_pos=(s2.x_km, s2.y_km),
                        tx_mast_height_m=s1.antenna_mast_m,
                        rx_mast_height_m=s2.antenna_mast_m,
                        frequency_mhz=prof.frequency_mhz,
                    )
                    assessment = RadioPropagationModel.evaluate_link(
                        los=los,
                        profile=prof,
                        rain_rate_mm_h=rain_rate_mm_h,
                        forest_density=(self.terrain.get_forest_density_at(s1.x_km, s1.y_km) + self.terrain.get_forest_density_at(s2.x_km, s2.y_km)) / 2.0,
                    )
                    if assessment.link_status in ("ACTIVE", "DEGRADED"):
                        best_assessment = assessment
                        break
                    if best_assessment is None:
                        best_assessment = assessment

                assessment = best_assessment

                pair_key = (n1, n2)
                self.link_assessments[pair_key] = assessment
                self.link_assessments[(n2, n1)] = assessment

                # Check manual cut override
                is_manually_cut = frozenset({n1, n2}) in self._manual_cuts

                # Edge viability criteria:
                # 1. Both stations alive
                # 2. Not manually severed
                # 3. Link status is not BLOCKED (margin >= 0 dB)
                if nodes_alive and not is_manually_cut and assessment.link_status in ("ACTIVE", "DEGRADED"):
                    # Routing cost function: Latency + penalty for degraded link margins
                    margin_penalty = max(1.0, (15.0 - assessment.link_margin_db) * 4.0) if assessment.link_margin_db < 15.0 else 0.0
                    weight = assessment.one_way_latency_ms + margin_penalty

                    self.graph.add_edge(
                        n1,
                        n2,
                        weight=round(weight, 1),
                        status=assessment.link_status,
                        margin_db=assessment.link_margin_db,
                        per=assessment.packet_error_rate,
                        throughput_bps=assessment.effective_throughput_bps,
                        latency_ms=assessment.one_way_latency_ms,
                        distance_km=assessment.distance_3d_km,
                        has_los=assessment.has_los,
                    )

    def get_route(self, source_id: str, destination_id: str) -> Optional[List[str]]:
        """
        Calculate optimal multi-hop route between source and destination using Dijkstra's algorithm.
        Returns ordered list of node IDs [source, relay1, relay2, ..., destination], or None if unreachable.
        """
        if source_id not in self.graph or destination_id not in self.graph:
            return None
        if source_id == destination_id:
            return [source_id]

        try:
            path = nx.shortest_path(self.graph, source=source_id, target=destination_id, weight="weight")
            return path
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return None

    def get_all_routes_for_node(self, source_id: str) -> Dict[str, Optional[List[str]]]:
        """Compute shortest paths from source_id to every other station."""
        routes = {}
        for target in self.stations.keys():
            if target == source_id:
                continue
            routes[target] = self.get_route(source_id, target)
        return routes

    def get_connected_components(self) -> List[List[str]]:
        """Return list of isolated network components / islands."""
        components = [sorted(list(c)) for c in nx.connected_components(self.graph)]
        # Include completely isolated/dead nodes
        all_nodes = set(self.stations.keys())
        in_components = set(n for c in components for n in c)
        for missing in all_nodes - in_components:
            components.append([missing])
        return sorted(components, key=lambda c: (len(c), c[0]), reverse=True)

    def cut_link(self, node_a: str, node_b: str) -> None:
        """Manually sever a radio link."""
        self._manual_cuts.add(frozenset({node_a, node_b}))
        if self.graph.has_edge(node_a, node_b):
            self.graph.remove_edge(node_a, node_b)

    def heal_link(self, node_a: str, node_b: str) -> None:
        """Clear manual cut for a radio link."""
        self._manual_cuts.discard(frozenset({node_a, node_b}))
        self.recompute_all_links()

    def heal_all_links(self) -> None:
        """Clear all manual cuts across the network."""
        self._manual_cuts.clear()
        self.recompute_all_links()

    def is_link_connected(self, node_a: str, node_b: str) -> bool:
        """Check if message can physically traverse direct hop between node_a and node_b."""
        return self.graph.has_edge(node_a, node_b)

    def get_link_info(self, node_a: str, node_b: str) -> Optional[Dict[str, Any]]:
        """Retrieve propagation assessment and graph edge status for a specific pair."""
        pair = (node_a, node_b)
        assessment = self.link_assessments.get(pair)
        if not assessment:
            return None

        is_connected = self.is_link_connected(node_a, node_b)
        is_manually_cut = frozenset({node_a, node_b}) in self._manual_cuts

        return {
            "node_a": node_a,
            "node_b": node_b,
            "is_connected": is_connected,
            "is_manually_cut": is_manually_cut,
            "status": "CUT" if is_manually_cut else assessment.link_status,
            "distance_km": assessment.distance_3d_km,
            "has_los": assessment.has_los,
            "margin_db": assessment.link_margin_db,
            "rx_power_dbm": assessment.rx_power_dbm,
            "snr_db": assessment.snr_db,
            "per": assessment.packet_error_rate,
            "throughput_bps": assessment.effective_throughput_bps,
            "latency_ms": assessment.one_way_latency_ms,
            "frequency_mhz": assessment.frequency_mhz,
            "free_space_loss_db": assessment.free_space_loss_db,
            "terrain_diffraction_loss_db": assessment.terrain_diffraction_loss_db,
        }

    def export_topology_data(self) -> Dict[str, Any]:
        """Telemetry snapshot for frontend visualization."""
        edges = []
        node_ids = list(self.stations.keys())

        for i in range(len(node_ids)):
            for j in range(i + 1, len(node_ids)):
                n1, n2 = node_ids[i], node_ids[j]
                info = self.get_link_info(n1, n2)
                if info:
                    edges.append(info)

        components = self.get_connected_components()
        routes = {}
        for nid in node_ids:
            routes[nid] = self.get_all_routes_for_node(nid)

        return {
            "total_stations": len(self.stations),
            "active_links": self.graph.number_of_edges(),
            "connected_components": components,
            "is_partitioned": len(components) > 1,
            "edges": edges,
            "routes": routes,
        }
