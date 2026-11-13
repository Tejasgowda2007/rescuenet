"""
FieldMesh: Digital Twin of Disaster-Response Communication Networks.
"""

from .terrain import TerrainModel, TerrainFeature, LineOfSightResult
from .radio import RadioPropagationModel, RadioProfile, RadioLinkAssessment, LORA_DEFAULT_PROFILE, DIRECTIONAL_P2P_PROFILE
from .stations import RescueStation, StationConfig, create_default_rescue_stations
from .topology import TopologyManager
from .packet import Packet, PacketFragmentationManager, PRIORITY_SOS, PRIORITY_SYNC, PRIORITY_TELEMETRY
from .engine import SimulationEngine
from .adapter import FieldMeshRadioTransport, create_rescuenet_nodes_for_fieldmesh
from .scenarios import ScenarioEngine, ScenarioPreset, SCENARIOS
from .metrics import MetricsAggregator
from .demo_runner import HackathonDemoRunner

__all__ = [
    "TerrainModel",
    "TerrainFeature",
    "LineOfSightResult",
    "RadioPropagationModel",
    "RadioProfile",
    "RadioLinkAssessment",
    "LORA_DEFAULT_PROFILE",
    "DIRECTIONAL_P2P_PROFILE",
    "RescueStation",
    "StationConfig",
    "create_default_rescue_stations",
    "TopologyManager",
    "Packet",
    "PacketFragmentationManager",
    "PRIORITY_SOS",
    "PRIORITY_SYNC",
    "PRIORITY_TELEMETRY",
    "SimulationEngine",
    "FieldMeshRadioTransport",
    "create_rescuenet_nodes_for_fieldmesh",
    "ScenarioEngine",
    "ScenarioPreset",
    "SCENARIOS",
    "MetricsAggregator",
    "HackathonDemoRunner",
]
