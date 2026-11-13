"""
FieldMesh FastAPI Backend & Live Telemetry Server.

Exposes REST endpoints and WebSocket stream for:
- 3D Terrain heightmap, geographic features, and coordinate projection.
- Stations management, battery levels, and independent SQLite stores.
- Radio link budgets, Line-of-Sight evaluations, and dynamic topology.
- Packet-level discrete-event simulation controls.
- 8 Disaster scenario presets and failure injection.
- 5-Minute Hackathon Demo workflow runner.
- Live telemetry metrics, latency percentiles, and invariant scorecard.
"""

from __future__ import annotations
import os
import sys
import asyncio
import time
from typing import Dict, List, Any, Optional
from contextlib import asynccontextmanager

# Ensure rescuenet root is on path
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, BackgroundTasks, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from auth.routes import auth_router
from auth.middleware import (
    get_current_user,
    require_admin,
    require_coordinator,
    require_responder,
    verify_ws_token,
)
from auth.database import init_admin_account

from fieldmesh import (
    TerrainModel,
    create_default_rescue_stations,
    TopologyManager,
    SimulationEngine,
    FieldMeshRadioTransport,
    create_rescuenet_nodes_for_fieldmesh,
    ScenarioEngine,
    SCENARIOS,
    MetricsAggregator,
    HackathonDemoRunner,
    Packet,
    PRIORITY_SOS,
    PRIORITY_SYNC,
)
from api.websocket import ws_manager
from allocation.escrow import EscrowManager
from allocation.tokens import TokenManager
from allocation.conflict_resolver import ConflictResolver


def broadcast_sync(message: Dict[str, Any]) -> None:
    """Safely schedule a WebSocket broadcast from synchronous endpoints."""
    if not ws_manager.active_connections:
        return
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(ws_manager.broadcast(message))
    except (RuntimeError, Exception):
        pass


# Pydantic Schemas for Requests
class EventRequest(BaseModel):
    node_id: str
    entity_type: str
    entity_id: str
    operation: str
    payload: Dict[str, Any]

class LinkToggleRequest(BaseModel):
    node_a: str
    node_b: str

class StationStatusRequest(BaseModel):
    status: str

class StationPositionRequest(BaseModel):
    x_km: float
    y_km: float

class StationCreateRequest(BaseModel):
    node_id: str
    name: str
    role: str
    x_km: float
    y_km: float
    antenna_mast_m: float = 12.0
    is_relay_only: bool = False
    has_p2p: bool = False

class ScenarioApplyRequest(BaseModel):
    scenario_id: str

class SimControlRequest(BaseModel):
    action: str  # "play", "pause", "step", "set_speed", "reset"
    speed: Optional[float] = None
    step_sec: Optional[float] = None

class SOSRequest(BaseModel):
    source_id: str
    message: str
    urgency: str = "CRITICAL"

class IncidentCreateRequest(BaseModel):
    node_id: str = "alpha"
    incident_id: Optional[str] = None
    id: Optional[str] = None
    title: str
    category: str = "MEDEVAC"
    severity: str = "HIGH"
    location: str = ""
    description: str = ""
    reported_by: str = "field-responder"
    assigned_teams: List[str] = Field(default_factory=list)

class MessageCreateRequest(BaseModel):
    message_id: Optional[str] = None
    id: Optional[str] = None
    node_id: str = "alpha"
    sender_id: str = "alpha"
    recipient_id: str = "ALL"
    content: str
    priority: str = "ROUTINE"  # CRITICAL, HIGH, ROUTINE
    location: str = ""

class IncidentStatusRequest(BaseModel):
    node_id: str = "alpha"
    status: Optional[str] = None
    resolution_notes: str = ""
    assign_team: Optional[str] = None

class VictimCreateRequest(BaseModel):
    node_id: str = "alpha"
    victim_id: str
    name: str
    triage_category: str = "YELLOW"
    status: str = "INJURED"
    medical_needs: str = ""
    location: str = ""
    contact_info: str = ""

class VictimTriageRequest(BaseModel):
    node_id: str = "alpha"
    triage_category: Optional[str] = None
    status: Optional[str] = None
    location: Optional[str] = None
    medical_needs: Optional[str] = None

class ShelterCreateRequest(BaseModel):
    node_id: str = "alpha"
    shelter_id: str
    name: str
    capacity: int
    location: str = ""

class ShelterOccupancyRequest(BaseModel):
    node_id: str = "alpha"
    occupancy: int

class SupplyPoolCreateRequest(BaseModel):
    node_id: str = "alpha"
    supply_id: str
    item_name: str
    total_quantity: int
    initial_quotas: Dict[str, int]
    unit: str = "units"

class SupplyConsumeRequest(BaseModel):
    node_id: str = "alpha"
    supply_id: str
    quantity: int
    beneficiary: str
    notes: str = ""

class SupplyTransferQuotaRequest(BaseModel):
    from_node_id: str = "alpha"
    to_node_id: str = "beta"
    supply_id: str
    quantity: int

class ScarceTokenRegisterRequest(BaseModel):
    node_id: str = "alpha"
    item_id: str
    item_name: str
    initial_holder_id: str = "alpha"
    category: str = "equipment"

class ScarceTokenRequestAction(BaseModel):
    node_id: str = "beta"
    item_id: str
    mission: str
    urgency: str = "HIGH"

class ScarceTokenConfirmAction(BaseModel):
    node_id: str = "alpha"
    item_id: str
    target_node_id: str = "beta"
    mission: str

class PeerRevokeRequest(BaseModel):
    node_id: str = "alpha"
    target_peer_id: str
    reason: str = "API_REVOCATION"


# Global FieldMesh State Container
class FieldMeshState:
    def __init__(self, data_dir: Optional[str] = None):
        self.terrain = TerrainModel(seed=42)
        effective_data_dir = data_dir or os.environ.get("RESCUENET_DATA_DIR")
        if not effective_data_dir:
            import tempfile
            default_dir = os.path.join(ROOT_DIR, "data")
            try:
                os.makedirs(default_dir, exist_ok=True)
                test_f = os.path.join(default_dir, ".perm_test")
                with open(test_f, "w") as tf:
                    tf.write("ok")
                os.remove(test_f)
                effective_data_dir = default_dir
            except Exception:
                effective_data_dir = os.path.join(tempfile.gettempdir(), "rescuenet_data")
                os.makedirs(effective_data_dir, exist_ok=True)

        self.stations = create_default_rescue_stations(self.terrain, data_dir=effective_data_dir)
        self.topology = TopologyManager(self.terrain, self.stations)
        self.engine = SimulationEngine(self.terrain, self.stations, self.topology, seed=42)
        self.transport = FieldMeshRadioTransport(self.topology, self.engine)
        self.nodes = create_rescuenet_nodes_for_fieldmesh(self.stations, self.transport)
        self.scenarios = ScenarioEngine(self.terrain, self.stations, self.topology, self.engine)
        self.metrics = MetricsAggregator(self.stations, self.topology, self.engine)
        self.demo = HackathonDemoRunner(self.terrain, self.stations, self.topology, self.engine, self.transport)

        # Seed initial pools
        self.scenarios.bootstrap_baseline_resources()
        # Start discrete-event background worker
        self.engine.start_background_loop(tick_interval_sec=0.1)


state = FieldMeshState()


# Background broadcast worker for WebSocket clients
async def telemetry_broadcaster():
    """Stream live telemetry packets and topology state to frontend at 4 Hz."""
    while True:
        try:
            pt = state.metrics.sample_tick()
            msg = {
                "type": "TELEMETRY_TICK",
                "sim_time": pt.sim_time_sec,
                "metrics": state.metrics.compute_live_metrics(),
                "stations": {nid: s.to_dict() for nid, s in state.stations.items()},
                "recent_packets": [
                    {
                        "id": r.packet_id,
                        "src": r.hop_source,
                        "dst": r.hop_target,
                        "type": r.msg_type,
                        "delivered": r.delivered,
                        "bytes": r.bytes_count,
                        "start": r.start_sim_time,
                        "end": r.end_sim_time,
                    }
                    for r in state.engine.transmission_log[-12:]
                ],
            }
            await ws_manager.broadcast(msg)
        except Exception:
            pass
        await asyncio.sleep(0.25)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize initial administrator account
    init_admin_account()

    # Startup: launch background broadcaster if not running under automated tests
    is_testing = "PYTEST_CURRENT_TEST" in os.environ or os.environ.get("RESCUENET_TEST_MODE") == "1"
    broadcaster_task = None
    if not is_testing:
        broadcaster_task = asyncio.create_task(telemetry_broadcaster())
    yield
    # Shutdown: stop simulation and broadcaster
    if broadcaster_task is not None:
        broadcaster_task.cancel()
    state.engine.stop()


app = FastAPI(
    title="RescueNet FieldMesh Digital Twin API",
    description="Offline-First Mountainous Disaster Mesh Network Simulator API",
    version="2.0.0",
    lifespan=lifespan,
)

# Enable CORS for local Vite dev server (e.g. port 5173) and any browser origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount Authentication Router (/api/auth/login, /logout, /me, /users, etc.)
app.include_router(auth_router)


# -------------------------------------------------------------
# REST ENDPOINTS: TERRAIN & GEOGRAPHY
# -------------------------------------------------------------

@app.get("/api/terrain")
def get_terrain_data():
    """Retrieve 3D elevation heightmap and feature coordinates for Three.js rendering."""
    return state.terrain.export_subsampled_grid(step=4)


# -------------------------------------------------------------
# REST ENDPOINTS: STATIONS
# -------------------------------------------------------------

@app.get("/api/stations", dependencies=[Depends(get_current_user)])
def list_stations():
    """List all rescue stations with live telemetry, battery, and coordinates."""
    return [s.to_dict() for s in state.stations.values()]

@app.get("/api/stations/{station_id}", dependencies=[Depends(get_current_user)])
def get_station_detail(station_id: str):
    """Retrieve full station inspection record."""
    if station_id not in state.stations:
        raise HTTPException(status_code=404, detail="Station not found")
    stn = state.stations[station_id]
    all_events = stn.store.get_all_events()
    events_list = [
        {
            "event_id": ev.event_id,
            "node_id": ev.node_id,
            "counter": ev.counter,
            "timestamp": ev.timestamp,
            "entity_type": ev.entity_type,
            "entity_id": ev.entity_id,
            "operation": ev.operation,
            "payload": ev.payload,
            "signature": ev.signature,
        }
        for ev in all_events
    ]
    return {
        "detail": stn.to_dict(),
        "routes": state.topology.get_all_routes_for_node(station_id),
        "version_vector": stn.get_version_vector(),
        "materialized_state": stn.get_materialized_state(),
        "events": events_list,
    }

@app.post("/api/stations", dependencies=[Depends(require_coordinator)])
def create_station(req: StationCreateRequest):
    """Add a new custom station to the simulation."""
    from fieldmesh.stations import StationConfig, RescueStation
    cfg = StationConfig(
        node_id=req.node_id,
        name=req.name,
        role=req.role,
        x_km=req.x_km,
        y_km=req.y_km,
        antenna_mast_m=req.antenna_mast_m,
        is_relay_only=req.is_relay_only,
        has_directional_p2p=req.has_p2p,
    )
    stn = RescueStation(config=cfg, terrain=state.terrain)
    state.stations[req.node_id] = stn
    # Re-wrap RescueNet node and recompute topology
    from fieldmesh.adapter import create_rescuenet_nodes_for_fieldmesh
    state.nodes = create_rescuenet_nodes_for_fieldmesh(state.stations, state.transport)
    state.topology.recompute_all_links()
    return stn.to_dict()

@app.post("/api/stations/{station_id}/status", dependencies=[Depends(require_coordinator)])
def set_station_status(station_id: str, req: StationStatusRequest):
    """Change station status (ONLINE, DEGRADED, DESTROYED)."""
    if station_id not in state.stations:
        raise HTTPException(status_code=404, detail="Station not found")
    stn = state.stations[station_id]
    if req.status.upper() == "DESTROYED":
        stn.destroy()
    elif req.status.upper() == "ONLINE":
        stn.restore()
    else:
        stn.status = req.status.upper()
    state.topology.recompute_all_links()
    return stn.to_dict()

@app.post("/api/stations/{station_id}/position", dependencies=[Depends(require_coordinator)])
def reposition_station(station_id: str, req: StationPositionRequest):
    """Move station coordinates across terrain."""
    if station_id not in state.stations:
        raise HTTPException(status_code=404, detail="Station not found")
    stn = state.stations[station_id]
    stn.set_position(req.x_km, req.y_km, state.terrain)
    state.topology.recompute_all_links()
    return stn.to_dict()


# -------------------------------------------------------------
# REST ENDPOINTS: TOPOLOGY & LINKS
# -------------------------------------------------------------

@app.get("/api/topology", dependencies=[Depends(get_current_user)])
def get_topology():
    """Retrieve full NetworkX graph topology and active routes."""
    return state.topology.export_topology_data()

@app.get("/api/links", dependencies=[Depends(get_current_user)])
def list_links():
    """List all radio links with link budgets, margins, and statuses."""
    return state.topology.export_topology_data()["edges"]

@app.post("/api/links/toggle", dependencies=[Depends(require_coordinator)])
def toggle_link(req: LinkToggleRequest):
    """Manually cut or heal a direct radio link."""
    n1, n2 = req.node_a, req.node_b
    if state.topology.is_link_connected(n1, n2):
        state.topology.cut_link(n1, n2)
        action = "CUT"
    else:
        state.topology.heal_link(n1, n2)
        action = "HEALED"
    return {"status": action, "link": state.topology.get_link_info(n1, n2)}

@app.post("/api/links/heal-all", dependencies=[Depends(require_coordinator)])
def heal_all_links():
    """Restore all radio links across the mesh."""
    state.topology.heal_all_links()
    return {"status": "ALL_LINKS_HEALED", "topology": state.topology.export_topology_data()}


# -------------------------------------------------------------
# REST ENDPOINTS: DISASTER SCENARIOS & REPLAY
# -------------------------------------------------------------

@app.get("/api/scenarios", dependencies=[Depends(get_current_user)])
def list_scenarios():
    """Return all 8 available disaster scenario presets."""
    return [
        {
            "id": s.id,
            "name": s.name,
            "hazard_type": s.hazard_type,
            "severity": s.severity,
            "description": s.description,
            "rain_mm_h": s.rain_rate_mm_h,
            "cut_links": s.cut_links,
            "destroyed_stations": s.destroyed_stations,
        }
        for s in SCENARIOS.values()
    ]

@app.post("/api/scenarios/apply", dependencies=[Depends(require_coordinator)])
def apply_scenario(req: ScenarioApplyRequest):
    """Apply a selected disaster scenario preset."""
    try:
        logs = state.scenarios.apply_scenario(req.scenario_id)
        return {"status": "SCENARIO_APPLIED", "scenario_id": req.scenario_id, "logs": logs}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

@app.post("/api/scenarios/reset", dependencies=[Depends(require_coordinator)])
def reset_scenario():
    """Reset network to 100% connected baseline."""
    state.scenarios.reset_to_clean_state()
    return {"status": "RESET_BASELINE"}


# -------------------------------------------------------------
# REST ENDPOINTS: ACTIONS & RESCUENET INTEGRATION
# -------------------------------------------------------------

@app.post("/api/actions/event", dependencies=[Depends(require_responder)])
def log_event(req: EventRequest):
    """Log an offline event (person, supply, boat, need, shelter) into a station's SQLite store."""
    if req.node_id not in state.stations:
        raise HTTPException(status_code=404, detail="Station not found")
    stn = state.stations[req.node_id]
    ev = stn.record_local_event(
        entity_type=req.entity_type,
        entity_id=req.entity_id,
        operation=req.operation,
        payload=req.payload,
    )
    return {"status": "EVENT_RECORDED", "event_id": ev.event_id, "counter": ev.counter}

@app.post("/api/actions/sync", dependencies=[Depends(require_responder)])
def trigger_sync(source_id: str, target_id: Optional[str] = None):
    """Execute anti-entropy delta synchronization over the simulated radio network."""
    if source_id not in state.nodes:
        raise HTTPException(status_code=404, detail=f"Source station {source_id} not found")

    src_node = state.nodes[source_id]
    results = []

    if target_id:
        stats = src_node.sync_with(target_id)
        results.append({"peer": target_id, "summary": stats.summary(), "success": stats.success})
    else:
        # Sync with all registered peers
        for peer_id in state.nodes.keys():
            if peer_id != source_id:
                stats = src_node.sync_with(peer_id)
                results.append({"peer": peer_id, "summary": stats.summary(), "success": stats.success})

    return {"status": "SYNC_COMPLETE", "results": results}

@app.post("/api/actions/sos", dependencies=[Depends(get_current_user)])
def trigger_sos(req: SOSRequest):
    """Broadcast high-priority emergency SOS message across the radio mesh."""
    if req.source_id not in state.stations:
        raise HTTPException(status_code=404, detail="Station not found")

    pkt = Packet(
        packet_id="",
        source_id=req.source_id,
        destination_id="BROADCAST",
        prev_hop=req.source_id,
        next_hop="",
        msg_type="SOS",
        priority=PRIORITY_SOS,
        payload={
            "source": req.source_id,
            "message": req.message,
            "urgency": req.urgency,
            "timestamp": time.time(),
        },
        ttl=6,
    )
    state.engine.schedule_packet(pkt)
    return {"status": "SOS_BROADCAST_SCHEDULED", "packet_id": pkt.packet_id}

@app.post("/api/actions/resolve-conflict", dependencies=[Depends(require_coordinator)])
def resolve_person_conflict(person_id: str, resolved_status: str, notes: str = "", station_id: str = "alpha"):
    """Resolve a flagged person conflict via human triage."""
    if station_id not in state.nodes:
        raise HTTPException(status_code=404, detail="Station not found")
    node = state.nodes[station_id]
    ev = ConflictResolver.resolve_person_conflict(
        node=node,
        person_id=person_id,
        verified_status=resolved_status,
        verified_location=f"Triage Base {station_id.upper()}",
        resolution_notes=notes,
    )
    return {"status": "CONFLICT_RESOLVED", "event_id": ev.event_id}


# -------------------------------------------------------------
# REST ENDPOINTS: RESCUENET CORE DOMAIN & NODE APIS
# -------------------------------------------------------------

@app.get("/api/nodes", dependencies=[Depends(get_current_user)])
def list_nodes():
    """List all disaster mesh nodes, version vectors, gaps, and health status."""
    result = []
    for nid, node in state.nodes.items():
        stn = state.stations.get(nid)
        gaps = node.store.get_all_gaps()
        result.append({
            "node_id": nid,
            "name": stn.config.name if stn else nid.upper(),
            "role": stn.config.role if stn else "NODE",
            "events_count": node.store.count(),
            "version_vector": node.get_version_vector(),
            "max_version_vector": node.store.get_max_version_vector(),
            "gaps": gaps,
            "has_gaps": len(gaps) > 0,
            "peer_health": node.get_peer_health(),
            "strict_mode": node.strict_mode,
            "keyring_active": node.keyring is not None,
            "battery_pct": stn.battery.percentage if stn else 100.0,
            "status": stn.status if stn else "ONLINE",
            "coords": [stn.x_km, stn.y_km] if stn else [0.0, 0.0],
        })
    return result

@app.post("/api/nodes/{node_id}/sync", dependencies=[Depends(require_responder)])
def sync_node_endpoint(node_id: str, target_id: Optional[str] = None):
    """Trigger anti-entropy sync for node_id against specific target or all peers."""
    if node_id not in state.nodes:
        raise HTTPException(status_code=404, detail="Node not found")
    node = state.nodes[node_id]
    results = []
    targets = [target_id] if target_id else [p for p in state.nodes.keys() if p != node_id]
    for tid in targets:
        if tid in state.nodes:
            stats = node.sync_with(tid)
            results.append({
                "peer": tid,
                "summary": stats.summary(),
                "success": stats.success,
                "events_sent": stats.events_sent,
                "events_received": stats.events_received,
                "total_bytes": stats.total_bytes,
            })
    return {"status": "SYNC_COMPLETE", "node_id": node_id, "results": results}

@app.get("/api/incidents", dependencies=[Depends(get_current_user)])
def list_incidents(node_id: Optional[str] = None):
    """List all emergency incidents across converged stations."""
    all_incidents = {}
    target_nodes = [node_id] if (node_id and node_id in state.nodes) else list(state.nodes.keys())
    for nid in target_nodes:
        n_state = state.nodes[nid].get_state()
        incs = n_state.get("incident", {})
        for i_id, i_data in incs.items():
            if i_id not in all_incidents or i_data.get("_created_at", 0) > all_incidents[i_id].get("_created_at", 0):
                all_incidents[i_id] = i_data
    return sorted(list(all_incidents.values()), key=lambda x: x.get("_created_at", 0), reverse=True)

@app.post("/api/incidents", dependencies=[Depends(require_responder)])
def create_incident_endpoint(req: IncidentCreateRequest):
    """Create a new emergency disaster incident."""
    target_node = req.node_id if req.node_id in state.nodes else "alpha"
    node = state.nodes[target_node]
    iid = req.incident_id or req.id or f"inc-{int(time.time()*1000)%1000000}"
    payload = {
        "id": iid,
        "title": req.title,
        "category": req.category.upper(),
        "severity": req.severity.upper(),
        "location": req.location,
        "description": req.description,
        "reported_by": req.reported_by,
        "status": "OPEN",
        "assigned_teams": req.assigned_teams or [],
        "created_at": int(time.time() * 1000),
    }
    ev = node.record_event("incident", iid, "CREATE", payload)
    
    # Broadcast to connected WebSocket subscribers
    broadcast_sync({
        "type": "INCIDENT_UPDATE",
        "incident": payload,
        "event_id": ev.event_id,
        "node_id": target_node,
    })
    
    return {"status": "INCIDENT_CREATED", "incident_id": iid, "incident": payload, "event_id": ev.event_id}

@app.post("/api/incidents/{incident_id}/status", dependencies=[Depends(require_responder)])
def update_incident_status_endpoint(incident_id: str, req: IncidentStatusRequest):
    """Update incident status, assign teams, or close incident."""
    target_node = req.node_id if req.node_id in state.nodes else "alpha"
    node = state.nodes[target_node]

    if req.assign_team:
        ev = node.record_event("incident", incident_id, "ASSIGN_TEAM", {"team": req.assign_team})
        broadcast_sync({"type": "INCIDENT_UPDATE", "incident_id": incident_id, "status": "TEAM_ASSIGNED", "team": req.assign_team})
        return {"status": "TEAM_ASSIGNED", "team": req.assign_team, "event_id": ev.event_id}

    if req.status and req.status.upper() == "RESOLVED":
        ev = node.record_event("incident", incident_id, "CLOSE_INCIDENT", {"resolution_notes": req.resolution_notes})
        broadcast_sync({"type": "INCIDENT_UPDATE", "incident_id": incident_id, "status": "RESOLVED"})
        return {"status": "INCIDENT_RESOLVED", "event_id": ev.event_id}

    if req.status:
        ev = node.record_event("incident", incident_id, "UPDATE", {"status": req.status.upper()})
        broadcast_sync({"type": "INCIDENT_UPDATE", "incident_id": incident_id, "status": req.status.upper()})
        return {"status": "INCIDENT_UPDATED", "event_id": ev.event_id}

    raise HTTPException(status_code=400, detail="No status or team assignment provided")

@app.get("/api/messages", dependencies=[Depends(get_current_user)])
def list_messages(node_id: Optional[str] = None):
    """List emergency radio messages across mesh."""
    all_messages = {}
    target_nodes = [node_id] if (node_id and node_id in state.nodes) else list(state.nodes.keys())
    for nid in target_nodes:
        n_state = state.nodes[nid].get_state()
        msgs = n_state.get("message", {})
        for m_id, m_data in msgs.items():
            if m_id not in all_messages or m_data.get("_created_at", 0) > all_messages[m_id].get("_created_at", 0):
                all_messages[m_id] = m_data
    return sorted(list(all_messages.values()), key=lambda x: x.get("timestamp", x.get("_created_at", 0)), reverse=True)

@app.post("/api/messages", dependencies=[Depends(get_current_user)])
def send_message_endpoint(req: MessageCreateRequest):
    """Send emergency tactical radio message across the mesh."""
    target_node = req.node_id if req.node_id in state.nodes else "alpha"
    node = state.nodes[target_node]
    mid = req.message_id or req.id or f"msg-{int(time.time()*1000)%1000000}"
    payload = {
        "id": mid,
        "sender_id": req.sender_id,
        "recipient_id": req.recipient_id,
        "content": req.content,
        "priority": req.priority.upper(),
        "location": req.location,
        "timestamp": int(time.time() * 1000),
        "status": "DELIVERED",
    }
    ev = node.record_event("message", mid, "CREATE", payload)
    
    # Broadcast to live WebSocket clients
    broadcast_sync({
        "type": "NEW_MESSAGE",
        "message": payload,
        "event_id": ev.event_id,
        "node_id": target_node,
    })
    
    # Inject discrete-event packet into simulation engine
    try:
        pkt = Packet(
            packet_id=f"pkt-{mid}",
            source=req.sender_id,
            destination=req.recipient_id if req.recipient_id != "ALL" else "beta",
            msg_type="MESSAGE",
            priority=PRIORITY_SOS if req.priority.upper() == "CRITICAL" else PRIORITY_SYNC,
            payload=payload,
            bytes_size=len(req.content.encode("utf-8")) + 64,
        )
        state.engine.schedule_packet(pkt)
    except Exception:
        pass

    return {"status": "MESSAGE_SENT", "message_id": mid, "message": payload, "event_id": ev.event_id}

@app.get("/api/victims", dependencies=[Depends(get_current_user)])
def list_victims(node_id: str = "alpha"):
    """List medical victims and triage records."""
    if node_id not in state.nodes:
        raise HTTPException(status_code=404, detail="Node not found")
    node_state = state.nodes[node_id].get_state()
    victims = node_state.get("victim", {})
    return list(victims.values())

@app.post("/api/victims", dependencies=[Depends(require_responder)])
def register_victim_endpoint(req: VictimCreateRequest):
    """Register a new victim with medical triage category."""
    if req.node_id not in state.nodes:
        raise HTTPException(status_code=404, detail="Node not found")
    node = state.nodes[req.node_id]
    payload = {
        "name": req.name,
        "triage_category": req.triage_category.upper(),
        "status": req.status.upper(),
        "medical_needs": req.medical_needs,
        "location": req.location,
        "contact_info": req.contact_info,
    }
    ev = node.record_event("victim", req.victim_id, "CREATE", payload)
    return {"status": "VICTIM_REGISTERED", "victim_id": req.victim_id, "event_id": ev.event_id}

@app.post("/api/victims/{victim_id}/triage", dependencies=[Depends(require_responder)])
def update_victim_triage_endpoint(victim_id: str, req: VictimTriageRequest):
    """Update victim medical triage classification or status."""
    if req.node_id not in state.nodes:
        raise HTTPException(status_code=404, detail="Node not found")
    node = state.nodes[req.node_id]
    payload = {}
    if req.triage_category:
        payload["triage_category"] = req.triage_category.upper()
    if req.status:
        payload["status"] = req.status.upper()
    if req.location:
        payload["location"] = req.location
    if req.medical_needs:
        payload["medical_needs"] = req.medical_needs

    ev = node.record_event("victim", victim_id, "UPDATE_TRIAGE", payload)
    return {"status": "TRIAGE_UPDATED", "victim_id": victim_id, "event_id": ev.event_id}

@app.get("/api/shelters", dependencies=[Depends(get_current_user)])
def list_shelters(node_id: str = "alpha"):
    """List evacuation shelters and occupancy."""
    if node_id not in state.nodes:
        raise HTTPException(status_code=404, detail="Node not found")
    node_state = state.nodes[node_id].get_state()
    shelters = node_state.get("shelter", {})
    return list(shelters.values())

@app.post("/api/shelters", dependencies=[Depends(require_coordinator)])
def create_shelter_endpoint(req: ShelterCreateRequest):
    """Create a new evacuation shelter."""
    if req.node_id not in state.nodes:
        raise HTTPException(status_code=404, detail="Node not found")
    node = state.nodes[req.node_id]
    payload = {
        "name": req.name,
        "capacity": req.capacity,
        "occupancy": 0,
        "location": req.location,
        "status": "OPEN",
    }
    ev = node.record_event("shelter", req.shelter_id, "CREATE", payload)
    return {"status": "SHELTER_CREATED", "shelter_id": req.shelter_id, "event_id": ev.event_id}

@app.post("/api/shelters/{shelter_id}/occupancy", dependencies=[Depends(require_coordinator)])
def update_shelter_occupancy_endpoint(shelter_id: str, req: ShelterOccupancyRequest):
    """Update current shelter occupancy count."""
    if req.node_id not in state.nodes:
        raise HTTPException(status_code=404, detail="Node not found")
    node = state.nodes[req.node_id]
    ev = node.record_event("shelter", shelter_id, "UPDATE", {"occupancy": req.occupancy})
    return {"status": "OCCUPANCY_UPDATED", "shelter_id": shelter_id, "occupancy": req.occupancy, "event_id": ev.event_id}

@app.get("/api/resources", dependencies=[Depends(get_current_user)])
def get_resources(node_id: str = "alpha"):
    """Return supply pools, escrow allowances, and scarce item token status."""
    if node_id not in state.nodes:
        raise HTTPException(status_code=404, detail="Node not found")
    node_state = state.nodes[node_id].get_state()
    return {
        "supplies": node_state.get("supply", {}),
        "supply_intents": node_state.get("supply_intent", {}),
        "scarce_items": node_state.get("scarce_item", {}),
        "needs": node_state.get("need", {}),
    }

@app.post("/api/resources/pool", dependencies=[Depends(require_coordinator)])
def create_resource_pool_endpoint(req: SupplyPoolCreateRequest):
    """Create an escrow-backed divisible supply pool."""
    if req.node_id not in state.nodes:
        raise HTTPException(status_code=404, detail="Node not found")
    node = state.nodes[req.node_id]
    ev = EscrowManager.create_pool(
        node=node,
        supply_id=req.supply_id,
        item_name=req.item_name,
        total_quantity=req.total_quantity,
        initial_quotas=req.initial_quotas,
        unit=req.unit,
    )
    return {"status": "POOL_CREATED", "supply_id": req.supply_id, "event_id": ev.event_id}

@app.post("/api/resources/consume", dependencies=[Depends(require_responder)])
def consume_resource_endpoint(req: SupplyConsumeRequest):
    """Consume from local node's escrow quota."""
    if req.node_id not in state.nodes:
        raise HTTPException(status_code=404, detail="Node not found")
    node = state.nodes[req.node_id]
    try:
        ev = EscrowManager.consume(
            node=node,
            supply_id=req.supply_id,
            quantity=req.quantity,
            beneficiary=req.beneficiary,
            notes=req.notes,
        )
        return {"status": "SUPPLY_CONSUMED", "quantity": req.quantity, "event_id": ev.event_id}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/resources/transfer-quota", dependencies=[Depends(require_coordinator)])
def transfer_quota_endpoint(req: SupplyTransferQuotaRequest):
    """Transfer escrow quota between nodes."""
    if req.from_node_id not in state.nodes or req.to_node_id not in state.nodes:
        raise HTTPException(status_code=404, detail="Node not found")
    node = state.nodes[req.from_node_id]
    try:
        ev = EscrowManager.transfer_quota(
            from_node=node,
            supply_id=req.supply_id,
            to_node_id=req.to_node_id,
            quantity=req.quantity,
        )
        return {"status": "QUOTA_TRANSFERRED", "to": req.to_node_id, "quantity": req.quantity, "event_id": ev.event_id}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/resources/token/register", dependencies=[Depends(require_coordinator)])
def register_scarce_token_endpoint(req: ScarceTokenRegisterRequest):
    """Register scarce asset token and assign genesis holder."""
    if req.node_id not in state.nodes:
        raise HTTPException(status_code=404, detail="Node not found")
    node = state.nodes[req.node_id]
    ev = TokenManager.register_item(
        node=node,
        item_id=req.item_id,
        item_name=req.item_name,
        initial_holder_id=req.initial_holder_id,
        category=req.category,
    )
    return {"status": "TOKEN_REGISTERED", "item_id": req.item_id, "holder": req.initial_holder_id, "event_id": ev.event_id}

@app.post("/api/resources/token/request", dependencies=[Depends(require_responder)])
def request_scarce_token_endpoint(req: ScarceTokenRequestAction):
    """Request allocation for a scarce indivisible item."""
    if req.node_id not in state.nodes:
        raise HTTPException(status_code=404, detail="Node not found")
    node = state.nodes[req.node_id]
    ev = TokenManager.request_allocation(
        node=node,
        item_id=req.item_id,
        mission_description=req.mission,
        urgency=req.urgency,
    )
    return {"status": "ALLOCATION_REQUESTED", "item_id": req.item_id, "event_id": ev.event_id}

@app.post("/api/resources/token/confirm", dependencies=[Depends(require_coordinator)])
def confirm_scarce_token_endpoint(req: ScarceTokenConfirmAction):
    """Confirm scarce asset allocation (verified by token holder)."""
    if req.node_id not in state.nodes:
        raise HTTPException(status_code=404, detail="Node not found")
    node = state.nodes[req.node_id]
    try:
        ev = TokenManager.confirm_allocation(
            node=node,
            item_id=req.item_id,
            assigned_to_mission=req.mission,
            target_node_id=req.target_node_id,
        )
        return {"status": "ALLOCATION_CONFIRMED", "item_id": req.item_id, "assigned_to": req.target_node_id, "event_id": ev.event_id}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/events", dependencies=[Depends(get_current_user)])
def query_events_endpoint(
    node_id: str = "alpha",
    entity_type: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
):
    """Paginated search over the immutable append-only event log."""
    if node_id not in state.nodes:
        raise HTTPException(status_code=404, detail="Node not found")
    node = state.nodes[node_id]
    events, total = node.store.query_events(
        entity_type=entity_type,
        limit=limit,
        offset=offset,
    )
    return {
        "node_id": node_id,
        "total": total,
        "limit": limit,
        "offset": offset,
        "events": [
            {
                "event_id": e.event_id,
                "node_id": e.node_id,
                "counter": e.counter,
                "timestamp": e.timestamp,
                "entity_type": e.entity_type,
                "entity_id": e.entity_id,
                "operation": e.operation,
                "payload": e.payload,
                "signature": e.signature,
            }
            for e in events
        ],
    }

@app.get("/api/security/peers", dependencies=[Depends(require_admin)])
def get_security_peers(node_id: str = "alpha"):
    """Return trusted and revoked peer public keys and SHA-256 fingerprints."""
    if node_id not in state.nodes:
        raise HTTPException(status_code=404, detail="Node not found")
    node = state.nodes[node_id]
    if not node.keyring:
        return {
            "keyring_active": False,
            "node_id": node_id,
            "trusted_peers": {},
            "revoked_peers": [],
        }

    from crypto.peer_manifest import compute_key_fingerprint
    peers_info = {}
    for pid, pkey in node.keyring.trusted_peers.items():
        peers_info[pid] = {
            "public_key": pkey,
            "fingerprint": compute_key_fingerprint(pkey),
        }

    return {
        "keyring_active": True,
        "node_id": node_id,
        "public_key": node.keyring.public_key_hex,
        "fingerprint": compute_key_fingerprint(node.keyring.public_key_hex) if node.keyring.public_key_hex else "",
        "trusted_peers": peers_info,
        "revoked_peers": list(node.keyring.revoked_peers),
    }

@app.post("/api/security/revoke", dependencies=[Depends(require_admin)])
def revoke_peer_endpoint(req: PeerRevokeRequest):
    """Revoke a peer node across the cluster."""
    if req.node_id not in state.nodes:
        raise HTTPException(status_code=404, detail="Node not found")
    node = state.nodes[req.node_id]
    if not node.keyring:
        raise HTTPException(status_code=400, detail="Keyring not active on this node")

    node.keyring.revoke_peer(req.target_peer_id, reason=req.reason)
    return {"status": "PEER_REVOKED", "target": req.target_peer_id, "reason": req.reason}

@app.get("/api/security/audit", dependencies=[Depends(require_admin)])
def get_security_audit_logs():
    """Retrieve security drop telemetry and tampering logs across all nodes."""
    logs = []
    for nid, node in state.nodes.items():
        for drop in node.security_drop_log:
            logs.append({"detector_node": nid, **drop})
    return sorted(logs, key=lambda x: x.get("timestamp", 0.0), reverse=True)


# -------------------------------------------------------------
# REST ENDPOINTS: 5-MINUTE HACKATHON DEMO RUNNER
# -------------------------------------------------------------

@app.get("/api/demo/status", dependencies=[Depends(get_current_user)])
def get_demo_status():
    """Retrieve demo step history and current step pointer."""
    return {
        "current_step": state.demo.current_step,
        "history": [
            {
                "step": r.step_number,
                "title": r.title,
                "description": r.description,
                "actions": r.actions_taken,
                "invariants": r.invariants_verified,
            }
            for r in state.demo.step_history
        ],
    }

@app.post("/api/demo/step/{step_number}", dependencies=[Depends(require_coordinator)])
def execute_demo_step(step_number: int):
    """Run an individual step (1 to 7) of the 5-minute hackathon demo."""
    if step_number == 1:
        res = state.demo.run_step_1_baseline_connected()
    elif step_number == 2:
        res = state.demo.run_step_2_mountain_obstruction()
    elif step_number == 3:
        res = state.demo.run_step_3_independent_offline_operations()
    elif step_number == 4:
        res = state.demo.run_step_4_activate_echo_relay()
    elif step_number == 5:
        res = state.demo.run_step_5_multi_hop_delta_sync()
    elif step_number == 6:
        res = state.demo.run_step_6_verify_convergence_and_invariants()
    elif step_number == 7:
        res = state.demo.run_step_7_human_triage_resolution()
    else:
        raise HTTPException(status_code=400, detail="Invalid demo step number (1-7)")

    return {
        "step": res.step_number,
        "title": res.title,
        "description": res.description,
        "actions": res.actions_taken,
        "invariants": res.invariants_verified,
    }

@app.post("/api/demo/reset", dependencies=[Depends(require_coordinator)])
def reset_demo():
    """Reset demo state back to step 0."""
    state.demo = HackathonDemoRunner(state.terrain, state.stations, state.topology, state.engine, state.transport)
    state.scenarios.reset_to_clean_state()
    return {"status": "DEMO_RESET"}


# -------------------------------------------------------------
# REST ENDPOINTS: METRICS & EXPERIMENT REPORTS
# -------------------------------------------------------------

@app.get("/api/metrics", dependencies=[Depends(get_current_user)])
def get_live_metrics():
    """Retrieve live computed telemetry KPIs and invariant status."""
    return state.metrics.compute_live_metrics()

@app.get("/api/metrics/timeseries", dependencies=[Depends(get_current_user)])
def get_metrics_timeseries():
    """Retrieve time-series history arrays for dashboard charts."""
    return state.metrics.export_timeseries_chart_data()

@app.get("/api/packets", dependencies=[Depends(get_current_user)])
def get_packet_logs(limit: int = 50):
    """Retrieve recent packet transmission records."""
    recent = state.engine.transmission_log[-limit:][::-1]
    return [
        {
            "packet_id": r.packet_id,
            "original_id": r.original_msg_id,
            "source": r.source_id,
            "destination": r.destination_id,
            "hop_src": r.hop_source,
            "hop_dst": r.hop_target,
            "msg_type": r.msg_type,
            "priority": r.priority,
            "bytes": r.bytes_count,
            "start": r.start_sim_time,
            "end": r.end_sim_time,
            "latency_ms": round((r.end_sim_time - r.start_sim_time) * 1000.0, 1),
            "delivered": r.delivered,
            "reason": r.dropped_reason,
            "route": r.route_taken,
        }
        for r in recent
    ]

@app.post("/api/simulation/control", dependencies=[Depends(require_coordinator)])
def control_simulation(req: SimControlRequest):
    """Control discrete-event simulation engine (play, pause, step, speed)."""
    if req.action == "pause":
        state.engine.pause()
    elif req.action == "play":
        state.engine.resume()
    elif req.action == "step":
        state.engine.step(req.step_sec or 1.0)
    elif req.action == "set_speed":
        state.engine.set_speed(req.speed or 1.0)
    return state.engine.get_metrics_snapshot()


# -------------------------------------------------------------
# WEBSOCKET ENDPOINT
# -------------------------------------------------------------

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: Optional[str] = None):
    cookie_token = websocket.cookies.get("rescuenet_token")
    auth_token = token or cookie_token
    user = verify_ws_token(auth_token)
    if not user:
        await websocket.close(code=1008)
        return

    await ws_manager.connect(websocket)
    try:
        while True:
            # Keep-alive receive
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception:
        ws_manager.disconnect(websocket)


# -------------------------------------------------------------
# STATIC FRONTEND MOUNT (IF COMPILED)
# -------------------------------------------------------------
DIST_DIR = os.path.join(ROOT_DIR, "web", "dist")
if os.path.isdir(DIST_DIR):
    app.mount("/", StaticFiles(directory=DIST_DIR, html=True), name="frontend")
