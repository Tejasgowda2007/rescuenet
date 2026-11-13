"""
FieldMesh Rescue Stations Model.

Defines the 5 default disaster stations (ALPHA, BRAVO, CHARLIE, DELTA, ECHO)
plus dynamic user-added stations.
Each station has:
- Coordinates, antenna mast, elevation, and location type.
- Genuinely independent SQLite database for offline event persistence.
- Local event counter and version vector.
- Realistic battery and solar charging model.
- Transmission and reception queues.
- Configurable operational status (ONLINE, DEGRADED, POWER_DEPLETED, DESTROYED).
"""

from __future__ import annotations
import os
import time
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from storage.sqlite_store import SQLiteEventStore
from storage.projector import StateProjector
from crypto.keyring import NodeKeyring
from .terrain import TerrainModel
from .radio import RadioProfile, LORA_DEFAULT_PROFILE, DIRECTIONAL_P2P_PROFILE


DEFAULT_STORAGE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))


@dataclass
class BatteryState:
    capacity_watt_hours: float = 120.0     # 120 Wh rugged LiFePO4 battery pack
    current_charge_wh: float = 110.0
    voltage_v: float = 12.8
    idle_power_w: float = 0.25             # Low-power microcontroller standby
    rx_power_w: float = 0.65               # Continuous radio receiver listening
    tx_power_w: float = 2.40               # Radio transmission burst
    solar_panel_peak_w: float = 20.0       # Foldable portable solar panel
    is_charging: bool = True

    @property
    def percentage(self) -> float:
        return round(max(0.0, min(100.0, (self.current_charge_wh / self.capacity_watt_hours) * 100.0)), 1)

    def step(self, delta_hours: float, is_tx: bool = False, solar_irradiance_ratio: float = 0.7) -> float:
        """Advance battery drain / charge for delta_hours."""
        drain_rate_w = self.tx_power_w if is_tx else (self.idle_power_w + self.rx_power_w)
        generation_w = self.solar_panel_peak_w * max(0.0, min(1.0, solar_irradiance_ratio)) if self.is_charging else 0.0

        net_w = generation_w - drain_rate_w
        self.current_charge_wh = max(0.0, min(self.capacity_watt_hours, self.current_charge_wh + net_w * delta_hours))
        return self.percentage


@dataclass
class StationConfig:
    node_id: str
    name: str
    role: str                       # HQ, CLINIC, SHELTER, FOREST_PATROL, RELAY
    x_km: float
    y_km: float
    antenna_mast_m: float = 12.0
    db_path: str = ""
    is_relay_only: bool = False
    radio_profile: RadioProfile = field(default_factory=lambda: LORA_DEFAULT_PROFILE)
    has_directional_p2p: bool = False


class RescueStation:
    """
    A standalone rescue station with its own hardware profile, local SQLite database,
    event counter, queues, and battery model.
    """

    def __init__(
        self,
        config: StationConfig,
        terrain: TerrainModel,
        data_dir: str = DEFAULT_STORAGE_DIR,
        keyring: Optional[NodeKeyring] = None,
    ) -> None:
        self.config = config
        self.node_id = config.node_id
        self.name = config.name
        self.role = config.role
        self.x_km = config.x_km
        self.y_km = config.y_km
        self.antenna_mast_m = config.antenna_mast_m
        self.is_relay_only = config.is_relay_only
        self.has_directional_p2p = config.has_directional_p2p

        # Elevation from terrain model
        self.elevation_m = round(terrain.get_elevation_at(self.x_km, self.y_km), 1)
        self.lat, self.lon = terrain.to_lat_lon(self.x_km, self.y_km)

        # Operational status: ONLINE, PARTITIONED, DEGRADED, POWER_DEPLETED, DESTROYED
        self.status: str = "ONLINE"
        self.battery = BatteryState()

        # Telemetry counters
        self.tx_packet_count: int = 0
        self.rx_packet_count: int = 0
        self.dropped_packet_count: int = 0
        self.bytes_sent: int = 0
        self.bytes_received: int = 0
        self.last_seen_timestamp: float = time.time()

        # Packet queues (simulated memory / disk buffers)
        self.tx_queue: List[Any] = []
        self.rx_queue: List[Any] = []
        self.forwarding_buffer: List[Any] = []

        # Local independent SQLite Event Store and Projector
        os.makedirs(data_dir, exist_ok=True)
        if not config.db_path:
            db_path = os.path.join(data_dir, f"station_{self.node_id}.db")
        else:
            db_path = config.db_path

        self.store = SQLiteEventStore(db_path)
        self.projector = StateProjector()
        self.keyring = keyring

        # Initialize local counter from persistent store
        vv = self.store.get_version_vector()
        self._local_counter = vv.get(self.node_id, 0)

    @property
    def total_events_count(self) -> int:
        return self.store.count()

    def get_version_vector(self) -> Dict[str, int]:
        return self.store.get_version_vector()

    def get_materialized_state(self) -> Dict[str, Dict[str, Any]]:
        all_events = self.store.get_all_events()
        if self.keyring is not None:
            # Authorized decrypted view
            decrypted = []
            for ev in all_events:
                decrypted.append(
                    ev.__class__(
                        node_id=ev.node_id,
                        counter=ev.counter,
                        timestamp=ev.timestamp,
                        entity_type=ev.entity_type,
                        entity_id=ev.entity_id,
                        operation=ev.operation,
                        payload=self.keyring.decrypt_payload(ev.payload),
                        signature=ev.signature,
                        event_id=ev.event_id,
                    )
                )
            return self.projector.compute_state(decrypted)
        return self.projector.compute_state(all_events)

    def record_local_event(
        self,
        entity_type: str,
        entity_id: str,
        operation: str,
        payload: Dict[str, Any],
        timestamp: Optional[float] = None,
    ) -> Any:
        """
        Record a local disaster coordination action with zero network connectivity.
        Offline-first: immediately written to this station's independent SQLite store.
        """
        from events.event import Event

        self._local_counter += 1
        ts = timestamp if timestamp is not None else time.time()

        stored_payload = payload
        if self.keyring is not None:
            stored_payload = self.keyring.encrypt_payload(payload)

        event = Event(
            node_id=self.node_id,
            counter=self._local_counter,
            timestamp=ts,
            entity_type=entity_type,
            entity_id=entity_id,
            operation=operation,
            payload=stored_payload,
        )
        if self.keyring is not None:
            event = self.keyring.sign_event(event)

        self.store.append(event)
        self.last_seen_timestamp = ts
        return event

    def set_position(self, x_km: float, y_km: float, terrain: TerrainModel) -> None:
        """Reposition station and update elevation accordingly."""
        self.x_km = max(0.0, min(50.0, float(x_km)))
        self.y_km = max(0.0, min(50.0, float(y_km)))
        self.elevation_m = round(terrain.get_elevation_at(self.x_km, self.y_km), 1)
        self.lat, self.lon = terrain.to_lat_lon(self.x_km, self.y_km)

    def destroy(self, reason: str = "Catastrophic landslide destruction") -> None:
        """Simulate hardware loss or tower collapse."""
        self.status = "DESTROYED"
        self.battery.current_charge_wh = 0.0

    def restore(self) -> None:
        """Re-commission or repair station."""
        self.status = "ONLINE"
        self.battery.current_charge_wh = self.battery.capacity_watt_hours * 0.9

    def to_dict(self) -> Dict[str, Any]:
        """Telemetry representation for REST API and 3D visualization."""
        return {
            "id": self.node_id,
            "name": self.name,
            "role": self.role,
            "coords": [round(self.x_km, 2), round(self.y_km, 2)],
            "elevation_m": self.elevation_m,
            "lat": self.lat,
            "lon": self.lon,
            "antenna_mast_m": self.antenna_mast_m,
            "status": self.status,
            "is_relay_only": self.is_relay_only,
            "has_p2p": self.has_directional_p2p,
            "battery_pct": self.battery.percentage,
            "battery_wh": round(self.battery.current_charge_wh, 1),
            "events_count": self.total_events_count,
            "version_vector": self.get_version_vector(),
            "tx_packets": self.tx_packet_count,
            "rx_packets": self.rx_packet_count,
            "dropped_packets": self.dropped_packet_count,
            "bytes_sent": self.bytes_sent,
            "bytes_received": self.bytes_received,
            "queue_depth": len(self.tx_queue) + len(self.forwarding_buffer),
            "last_seen": self.last_seen_timestamp,
        }


def create_default_rescue_stations(terrain: TerrainModel, data_dir: str = DEFAULT_STORAGE_DIR) -> Dict[str, RescueStation]:
    """
    Instantiate the 5 standard disaster response stations across the 50x50 km zone.
    Notice strategic placements:
    - ALPHA (Valley Command HQ, SW)
    - BRAVO (Medical Clinic, West River valley)
    - CHARLIE (Mountain Shelter, NE across Trishul Ridge - heavily obstructed!)
    - DELTA (Forest Rescue, SE dense canopy)
    - ECHO (Elevated Relay Tower, Center-East Summit at 2,350m - line-of-sight to both sides!)
    """
    default_configs = [
        StationConfig(
            node_id="alpha",
            name="ALPHA Rescue HQ",
            role="HQ",
            x_km=10.5,
            y_km=8.2,
            antenna_mast_m=18.0,
            has_directional_p2p=True,
        ),
        StationConfig(
            node_id="bravo",
            name="BRAVO Medical Camp",
            role="CLINIC",
            x_km=18.4,
            y_km=22.1,
            antenna_mast_m=12.0,
            has_directional_p2p=False,
        ),
        StationConfig(
            node_id="charlie",
            name="CHARLIE Mountain Shelter",
            role="SHELTER",
            x_km=38.2,
            y_km=41.5,
            antenna_mast_m=15.0,
            has_directional_p2p=False,
        ),
        StationConfig(
            node_id="delta",
            name="DELTA Forest Patrol",
            role="FOREST_PATROL",
            x_km=31.0,
            y_km=14.8,
            antenna_mast_m=10.0,
            has_directional_p2p=False,
        ),
        StationConfig(
            node_id="echo",
            name="ECHO Elevated Relay",
            role="RELAY",
            x_km=22.0,
            y_km=25.0,
            antenna_mast_m=30.0,   # Tall relay tower on high mountain summit (2,800m)
            is_relay_only=True,
            has_directional_p2p=True,
        ),
    ]

    stations = {}
    for cfg in default_configs:
        station = RescueStation(config=cfg, terrain=terrain, data_dir=data_dir)
        stations[cfg.node_id] = station

    return stations
