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

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

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


# Global FieldMesh State Container
class FieldMeshState:
    def __init__(self):
        self.terrain = TerrainModel(seed=42)
        self.stations = create_default_rescue_stations(self.terrain)
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
    # Startup: launch background broadcaster
    broadcaster_task = asyncio.create_task(telemetry_broadcaster())
    yield
    # Shutdown: stop simulation and broadcaster
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

@app.get("/api/stations")
def list_stations():
    """List all rescue stations with live telemetry, battery, and coordinates."""
    return [s.to_dict() for s in state.stations.values()]

@app.get("/api/stations/{station_id}")
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

@app.post("/api/stations")
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

@app.post("/api/stations/{station_id}/status")
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

@app.post("/api/stations/{station_id}/position")
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

@app.get("/api/topology")
def get_topology():
    """Retrieve full NetworkX graph topology and active routes."""
    return state.topology.export_topology_data()

@app.get("/api/links")
def list_links():
    """List all radio links with link budgets, margins, and statuses."""
    return state.topology.export_topology_data()["edges"]

@app.post("/api/links/toggle")
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

@app.post("/api/links/heal-all")
def heal_all_links():
    """Restore all radio links across the mesh."""
    state.topology.heal_all_links()
    return {"status": "ALL_LINKS_HEALED", "topology": state.topology.export_topology_data()}


# -------------------------------------------------------------
# REST ENDPOINTS: DISASTER SCENARIOS & REPLAY
# -------------------------------------------------------------

@app.get("/api/scenarios")
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

@app.post("/api/scenarios/apply")
def apply_scenario(req: ScenarioApplyRequest):
    """Apply a selected disaster scenario preset."""
    try:
        logs = state.scenarios.apply_scenario(req.scenario_id)
        return {"status": "SCENARIO_APPLIED", "scenario_id": req.scenario_id, "logs": logs}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

@app.post("/api/scenarios/reset")
def reset_scenario():
    """Reset network to 100% connected baseline."""
    state.scenarios.reset_to_clean_state()
    return {"status": "RESET_BASELINE"}


# -------------------------------------------------------------
# REST ENDPOINTS: ACTIONS & RESCUENET INTEGRATION
# -------------------------------------------------------------

@app.post("/api/actions/event")
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

@app.post("/api/actions/sync")
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

@app.post("/api/actions/sos")
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

@app.post("/api/actions/resolve-conflict")
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
# REST ENDPOINTS: 5-MINUTE HACKATHON DEMO RUNNER
# -------------------------------------------------------------

@app.get("/api/demo/status")
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

@app.post("/api/demo/step/{step_number}")
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

@app.post("/api/demo/reset")
def reset_demo():
    """Reset demo state back to step 0."""
    state.demo = HackathonDemoRunner(state.terrain, state.stations, state.topology, state.engine, state.transport)
    state.scenarios.reset_to_clean_state()
    return {"status": "DEMO_RESET"}


# -------------------------------------------------------------
# REST ENDPOINTS: METRICS & EXPERIMENT REPORTS
# -------------------------------------------------------------

@app.get("/api/metrics")
def get_live_metrics():
    """Retrieve live computed telemetry KPIs and invariant status."""
    return state.metrics.compute_live_metrics()

@app.get("/api/metrics/timeseries")
def get_metrics_timeseries():
    """Retrieve time-series history arrays for dashboard charts."""
    return state.metrics.export_timeseries_chart_data()

@app.get("/api/packets")
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

@app.post("/api/simulation/control")
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
async def websocket_endpoint(websocket: WebSocket):
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
