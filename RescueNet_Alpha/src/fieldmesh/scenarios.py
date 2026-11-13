"""
FieldMesh Disaster Scenario Engine.

Provides 8 realistic multi-hazard disaster scenario presets:
1. Mountain Earthquake
2. Flash Flood
3. Forest Fire
4. Landslide
5. Complete Communication Blackout
6. Relay Tower Failure
7. Isolated Medical Camp
8. Multi-Region Partition

Supports custom failure injections, deterministic scenario replay,
and automatic event logging.
"""

from __future__ import annotations
import time
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from .terrain import TerrainModel
from .stations import RescueStation
from .topology import TopologyManager
from .engine import SimulationEngine
from allocation.escrow import EscrowManager
from allocation.tokens import TokenManager


@dataclass
class ScenarioPreset:
    id: str
    name: str
    hazard_type: str
    severity: str              # CRITICAL, HIGH, MODERATE
    description: str
    rain_rate_mm_h: float
    cut_links: List[tuple]
    destroyed_stations: List[str]
    isolated_nodes: List[str]
    initial_events: List[Dict[str, Any]]


SCENARIOS: Dict[str, ScenarioPreset] = {
    "mountain_earthquake": ScenarioPreset(
        id="mountain_earthquake",
        name="Mountain Earthquake (M6.8)",
        hazard_type="Earthquake",
        severity="CRITICAL",
        description="Magnitude 6.8 tremor causes massive rockslides in the Trishul Ridge pass. Direct valley radio paths are severed.",
        rain_rate_mm_h=10.0,
        cut_links=[("alpha", "charlie"), ("alpha", "delta")],
        destroyed_stations=[],
        isolated_nodes=["charlie"],
        initial_events=[
            {"node": "alpha", "type": "need", "id": "need-generators", "op": "CREATE", "payload": {"item": "Heavy Diesel Generators", "urgency": "CRITICAL"}},
            {"node": "charlie", "type": "shelter", "id": "shelter-plateau", "op": "CREATE", "payload": {"name": "High Alpine Shelter", "capacity": 150, "occupancy": 84}},
        ],
    ),
    "flash_flood": ScenarioPreset(
        id="flash_flood",
        name="Bhagirathi Gorge Flash Flood",
        hazard_type="Flood",
        severity="CRITICAL",
        description="Glacial outburst floods the western valley gorge. Suspension Bridge #4 is swept away. Rescue boat deployment is vital.",
        rain_rate_mm_h=65.0,  # Torrential monsoon downpour
        cut_links=[("alpha", "charlie"), ("bravo", "delta")],
        destroyed_stations=[],
        isolated_nodes=["charlie"],
        initial_events=[
            {"node": "alpha", "type": "person", "id": "person-dr-stone", "op": "UPDATE", "payload": {"name": "Dr. Elizabeth Stone", "status": "MISSING", "location": "Submerged Pier 2"}},
            {"node": "charlie", "type": "person", "id": "person-dr-stone", "op": "UPDATE", "payload": {"name": "Dr. Elizabeth Stone", "status": "FOUND_SAFE", "location": "Highland Evacuation Ridge"}},
        ],
    ),
    "forest_fire": ScenarioPreset(
        id="forest_fire",
        name="Trishul Forest Wildfire",
        hazard_type="Wildfire",
        severity="HIGH",
        description="Wildfire rages through the southern pine forest basin. Smoke particulates heavily attenuate high-frequency directional beams.",
        rain_rate_mm_h=0.0,
        cut_links=[("delta", "charlie"), ("delta", "echo")],
        destroyed_stations=[],
        isolated_nodes=["delta"],
        initial_events=[
            {"node": "delta", "type": "need", "id": "need-burn-kits", "op": "CREATE", "payload": {"item": "Hydrogel Burn Dressings", "urgency": "CRITICAL"}},
        ],
    ),
    "landslide": ScenarioPreset(
        id="landslide",
        name="Highway 10 Monsoon Landslide",
        hazard_type="Landslide",
        severity="HIGH",
        description="Debris flow buries Highway 10. Direct link between Alpha and Bravo is disrupted by fallen power lines.",
        rain_rate_mm_h=35.0,
        cut_links=[("alpha", "bravo")],
        destroyed_stations=[],
        isolated_nodes=[],
        initial_events=[
            {"node": "bravo", "type": "need", "id": "need-blood-plasma", "op": "CREATE", "payload": {"item": "Type O Negative Plasma", "urgency": "CRITICAL"}},
        ],
    ),
    "complete_blackout": ScenarioPreset(
        id="complete_blackout",
        name="Complete RF Storm Blackout",
        hazard_type="Atmospheric Storm",
        severity="CRITICAL",
        description="Severe cyclonic geomagnetic storm severs all direct station-to-station radio links. Only the high mountain relay can establish contact.",
        rain_rate_mm_h=90.0,
        cut_links=[("alpha", "bravo"), ("alpha", "charlie"), ("alpha", "delta"), ("bravo", "charlie"), ("bravo", "delta"), ("charlie", "delta")],
        destroyed_stations=[],
        isolated_nodes=[],
        initial_events=[],
    ),
    "relay_failure": ScenarioPreset(
        id="relay_failure",
        name="ECHO Relay Tower Structural Collapse",
        hazard_type="Infrastructure Failure",
        severity="CRITICAL",
        description="A lightning strike destroys the primary antenna array at ECHO Elevated Relay. The network must discover a multi-hop ground detour.",
        rain_rate_mm_h=20.0,
        cut_links=[("alpha", "echo"), ("bravo", "echo"), ("charlie", "echo"), ("delta", "echo")],
        destroyed_stations=["echo"],
        isolated_nodes=[],
        initial_events=[
            {"node": "alpha", "type": "need", "id": "need-tower-riggers", "op": "CREATE", "payload": {"item": "Radio Repair Crew", "urgency": "HIGH"}},
        ],
    ),
    "isolated_medical_camp": ScenarioPreset(
        id="isolated_medical_camp",
        name="Isolated Trauma Camp Bravo",
        hazard_type="Isolation",
        severity="HIGH",
        description="Bravo Medical Clinic is cut off on all fronts. Volunteers must perform offline medical triage and consume local antibiotic escrow without central authority.",
        rain_rate_mm_h=15.0,
        cut_links=[("alpha", "bravo"), ("bravo", "echo"), ("bravo", "charlie"), ("bravo", "delta")],
        destroyed_stations=[],
        isolated_nodes=["bravo"],
        initial_events=[
            {"node": "bravo", "type": "person", "id": "person-casualty-101", "op": "UPDATE", "payload": {"name": "Aarav Patel", "status": "IN_SURGERY_STABLE", "location": "Trauma Tent B"}},
        ],
    ),
    "multi_region_partition": ScenarioPreset(
        id="multi_region_partition",
        name="Multi-Region Split (3 Islands)",
        hazard_type="Compound Disaster",
        severity="CRITICAL",
        description="Simultaneous floods and landslides fragment the response zone into 3 completely isolated clusters: [ALPHA], [BRAVO, DELTA], [CHARLIE, ECHO].",
        rain_rate_mm_h=45.0,
        cut_links=[("alpha", "bravo"), ("alpha", "echo"), ("alpha", "charlie"), ("bravo", "charlie"), ("delta", "charlie")],
        destroyed_stations=[],
        isolated_nodes=[],
        initial_events=[
            {"node": "alpha", "type": "person", "id": "person-dr-stone", "op": "UPDATE", "payload": {"name": "Dr. Elizabeth Stone", "status": "MISSING", "location": "Sector Alpha Harbor"}},
            {"node": "charlie", "type": "person", "id": "person-dr-stone", "op": "UPDATE", "payload": {"name": "Dr. Elizabeth Stone", "status": "FOUND_SAFE", "location": "Sector Charlie Mountain"}},
        ],
    ),
}


class ScenarioEngine:
    """
    Orchestrates disaster scenarios, failure injection schedules, and baseline resources.
    """

    def __init__(
        self,
        terrain: TerrainModel,
        stations: Dict[str, RescueStation],
        topology: TopologyManager,
        sim_engine: SimulationEngine,
    ) -> None:
        self.terrain = terrain
        self.stations = stations
        self.topology = topology
        self.sim_engine = sim_engine
        self.active_scenario: Optional[ScenarioPreset] = None
        self.scenario_start_time: float = time.time()
        self.activity_log: List[str] = []

    def bootstrap_baseline_resources(self) -> None:
        """
        Seed baseline divisible supply escrow pool (Antibiotics)
        and indivisible scarce asset token (Rescue Boat Titan) on Alpha HQ.
        """
        alpha = self.stations.get("alpha")
        if not alpha:
            return

        # 1. Escrow pool of 200 courses of antibiotics divided among stations
        initial_quotas = {
            "alpha": 80,
            "bravo": 60,
            "charlie": 30,
            "delta": 30,
        }
        try:
            EscrowManager.create_pool(
                node=alpha,
                supply_id="supply-antibiotics",
                item_name="Amoxicillin 500mg Courses",
                total_quantity=200,
                initial_quotas=initial_quotas,
                unit="courses",
            )
        except Exception:
            pass

        # 2. Single-Owner Token for Titan Rescue Boat #1
        try:
            TokenManager.register_item(
                node=alpha,
                item_id="boat-titan",
                item_name="Titan Rapid Flood Boat #1",
                initial_holder_id="alpha",
                location="Harbor Pier #1",
            )
        except Exception:
            pass

    def apply_scenario(self, scenario_id: str) -> List[str]:
        """
        Load and apply a disaster scenario preset.
        """
        if scenario_id not in SCENARIOS:
            raise KeyError(f"Unknown scenario ID: {scenario_id}")

        preset = SCENARIOS[scenario_id]
        self.active_scenario = preset
        self.scenario_start_time = time.time()

        # Step 1: Restore all stations and links first
        self.topology.heal_all_links()
        for s in self.stations.values():
            s.restore()

        # Step 2: Apply specific link cuts
        for n1, n2 in preset.cut_links:
            self.topology.cut_link(n1, n2)

        # Step 3: Destroy stations if applicable
        for nid in preset.destroyed_stations:
            if nid in self.stations:
                self.stations[nid].destroy(f"Destroyed in {preset.name}")

        # Step 4: Recompute radio propagation with rain rate
        self.topology.recompute_all_links(rain_rate_mm_h=preset.rain_rate_mm_h)

        # Step 5: Log initial scenario events into local SQLite databases
        for ev_def in preset.initial_events:
            nid = ev_def["node"]
            if nid in self.stations:
                self.stations[nid].record_local_event(
                    entity_type=ev_def["type"],
                    entity_id=ev_def["id"],
                    operation=ev_def["op"],
                    payload=ev_def["payload"],
                )

        log_msg = f"Applied scenario: {preset.name} ({preset.severity}) - Rain: {preset.rain_rate_mm_h} mm/h"
        self.activity_log.append(log_msg)
        return [log_msg]

    def reset_to_clean_state(self) -> None:
        """Clear all partitions, heal links, and restore all stations."""
        self.topology.heal_all_links()
        for s in self.stations.values():
            s.restore()
        self.active_scenario = None
        self.activity_log.append("Reset network to 100% connected baseline.")
