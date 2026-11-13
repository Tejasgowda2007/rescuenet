"""
RescueNet Unified Node Server for Three-Laptop Offline Mesh Deployment.

Runs an independent, peer-to-peer disaster coordination node on each laptop.
Combines:
  1. TCP Transport (port 8001) for point-to-point anti-entropy delta synchronization.
  2. UDP Peer Discovery Beacon (port 8002) for zero-config Wi-Fi/hotspot peer discovery.
  3. Ed25519 signing and AES-256-GCM Mesh PSK encryption (security/<node_id>).
  4. Persistent local SQLite database (data/<node_id>.db).
  5. Content-addressable offline attachments store (data/attachments/).
  6. FastAPI web server & WebSocket broadcaster (port 8000) serving the FieldMesh React UI.
"""

from __future__ import annotations
import argparse
import asyncio
import base64
import json
import os
import socket
import sys
import threading
import time
from typing import Dict, Any, List, Optional, Tuple

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

# Ensure project root is on sys.path
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from events.event import Event
from transport.tcp import TCPTransport
from transport.discovery import PeerDiscoveryBeacon
from sync.node import Node, StrictSecurityError
from sync.gossip import GossipSyncDaemon
from crypto.keyring import NodeKeyring
from storage.attachments import AttachmentManager


# -------------------------------------------------------------
# KNOWN MESH NODE PROFILES & METADATA
# -------------------------------------------------------------

NODE_PROFILES: Dict[str, Dict[str, Any]] = {
    "alpha-harbor": {
        "name": "Alpha Harbor Base",
        "role": "Harbor Command Center",
        "description": "Primary coastal coordination hub & incident command post",
        "coords": [12.92, 74.85],
        "x_km": 2.0,
        "y_km": 1.5,
        "antenna_mast_m": 15.0,
    },
    "beta-hospital": {
        "name": "Beta Field Hospital",
        "role": "Field Hospital and Medical Coordination",
        "description": "Central medical triage facility & emergency casualty staging",
        "coords": [12.97, 74.92],
        "x_km": 14.5,
        "y_km": 8.0,
        "antenna_mast_m": 12.0,
    },
    "gamma-mountain": {
        "name": "Gamma Mountain Relay",
        "role": "Mountain Shelter and Relay Station",
        "description": "High-altitude relay repeater & wilderness evacuation shelter",
        "coords": [13.05, 75.02],
        "x_km": 28.0,
        "y_km": 19.5,
        "antenna_mast_m": 25.0,
    },
}


def detect_local_ip() -> str:
    """Detect the active local IPv4 address of this machine."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # Does not send packets, just determines routing table choice
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return "127.0.0.1"


# -------------------------------------------------------------
# WEBSOCKET CONNECTION MANAGER
# -------------------------------------------------------------

class NodeWebSocketManager:
    """Manages active browser connections for real-time live dashboard sync."""

    def __init__(self) -> None:
        self.active_connections: List[WebSocket] = []
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self.active_connections.append(ws)

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            if ws in self.active_connections:
                self.active_connections.remove(ws)

    async def broadcast(self, message: Dict[str, Any]) -> None:
        async with self._lock:
            if not self.active_connections:
                return
            dead = []
            text = json.dumps(message)
            for ws in self.active_connections:
                try:
                    await ws.send_text(text)
                except Exception:
                    dead.append(ws)
            for ws in dead:
                if ws in self.active_connections:
                    self.active_connections.remove(ws)


ws_broadcaster = NodeWebSocketManager()


# -------------------------------------------------------------
# PYDANTIC SCHEMAS
# -------------------------------------------------------------

class IncidentRequest(BaseModel):
    incident_id: Optional[str] = None
    title: str
    severity: str = "HIGH"  # CRITICAL, HIGH, MEDIUM, LOW
    location: str = ""
    description: str = ""
    assigned_teams: List[str] = Field(default_factory=list)

class VictimRequest(BaseModel):
    victim_id: Optional[str] = None
    name: str
    triage_category: str = "YELLOW"  # RED, YELLOW, GREEN, BLACK
    status: str = "INJURED"  # TRAPPED, INJURED, STABLE, TREATED, EVACUATED
    medical_needs: str = ""
    location: str = ""
    contact_info: str = ""

class RescuerRequest(BaseModel):
    rescuer_id: Optional[str] = None
    name: str
    role: str = "Search & Rescue"
    status: str = "AVAILABLE"  # AVAILABLE, DEPLOYED, RESTING, OFFLINE
    team: str = "Alpha Team"
    location: str = ""
    callsign: str = ""

class SupplyRequest(BaseModel):
    supply_id: Optional[str] = None
    item_name: str
    quantity: int = 10
    unit: str = "units"
    is_need: bool = False
    urgency: str = "HIGH"
    location: str = ""

class AlertRequest(BaseModel):
    alert_id: Optional[str] = None
    title: str
    message: str
    severity: str = "CRITICAL"  # CRITICAL, WARNING, INFO

class ChatRequest(BaseModel):
    message_id: Optional[str] = None
    text: str
    channel: str = "general"
    sender_name: Optional[str] = None

class AddPeerRequest(BaseModel):
    peer_id: str
    host: str
    port: int

class GenericEventRequest(BaseModel):
    node_id: Optional[str] = None
    entity_type: str
    entity_id: str
    operation: str
    payload: Dict[str, Any]


# -------------------------------------------------------------
# NODE SERVICE CORE
# -------------------------------------------------------------

class RescueNetNodeService:
    """Coordinates all backend mesh components for a single laptop."""

    def __init__(
        self,
        node_id: str,
        host: str = "0.0.0.0",
        tcp_port: int = 8001,
        web_port: int = 8000,
        db_path: Optional[str] = None,
        security_dir: Optional[str] = None,
        mesh_psk_hex: Optional[str] = None,
        passphrase: Optional[str] = None,
        strict_security: bool = False,
        enable_discovery: bool = True,
        discovery_port: int = 8002,
        attachments_dir: Optional[str] = None,
        static_dir: Optional[str] = None,
    ) -> None:
        self.node_id = node_id
        self.host = host
        self.tcp_port = tcp_port
        self.web_port = web_port
        self.strict_security = strict_security
        self.enable_discovery = enable_discovery
        self.discovery_port = discovery_port
        self.local_ip = detect_local_ip()

        # Storage paths
        if not db_path:
            os.makedirs(os.path.join(ROOT_DIR, "data"), exist_ok=True)
            self.db_path = os.path.join(ROOT_DIR, "data", f"{node_id}.db")
        else:
            self.db_path = db_path

        self.attachments_dir = attachments_dir or os.path.join(ROOT_DIR, "data", "attachments")
        self.attachment_mgr = AttachmentManager(self.attachments_dir)
        self.static_dir = static_dir or os.path.join(ROOT_DIR, "web", "dist")

        # 1. Initialize TCP Transport
        self.transport = TCPTransport(node_id=self.node_id, host=self.host, port=self.tcp_port)
        # Actual port if 0 was passed
        self.tcp_port = self.transport.port

        # 2. Initialize Security / Keyring
        self.keyring = self._setup_keyring(security_dir, mesh_psk_hex, passphrase)

        # 3. Initialize Node & Store
        self.node = Node(
            node_id=self.node_id,
            db_path=self.db_path,
            transport=self.transport,
            keyring=self.keyring,
            strict_mode=self.strict_security,
        )

        # 4. Initialize Gossip Daemon
        self.gossip = GossipSyncDaemon(node=self.node, interval_sec=3.0)
        self.node.gossip_daemon = self.gossip
        self.gossip.start()

        # 5. Register Event Listener for Push Updates & Attachments
        self.node.register_event_listener(self._handle_new_event)

        # 6. Initialize Peer Discovery Beacon
        self.discovery: Optional[PeerDiscoveryBeacon] = None
        if self.enable_discovery:
            trusted_ids = list(self.keyring.trusted_peers.keys()) if (self.keyring and self.keyring.trusted_peers) else None
            self.discovery = PeerDiscoveryBeacon(
                node_id=self.node_id,
                tcp_port=self.tcp_port,
                web_port=self.web_port,
                broadcast_port=self.discovery_port,
                on_peer_discovered=self._on_peer_discovered,
                on_peer_lost=self._on_peer_lost,
                trusted_peer_ids=trusted_ids,
            )
            self.discovery.start()

        # 7. Start Async Background Loop reference
        self.async_loop: Optional[asyncio.AbstractEventLoop] = None

    def _setup_keyring(
        self,
        security_dir: Optional[str],
        mesh_psk_hex: Optional[str],
        passphrase: Optional[str],
    ) -> Optional[NodeKeyring]:
        """Load and configure node cryptographic credentials."""
        sec_dir = security_dir or os.path.join(ROOT_DIR, "security")
        node_sec_dir = os.path.join(sec_dir, self.node_id)

        effective_psk = mesh_psk_hex
        if not effective_psk and os.path.exists(node_sec_dir):
            cfg_file = os.path.join(node_sec_dir, "mesh_config.json")
            if os.path.exists(cfg_file):
                try:
                    with open(cfg_file, "r", encoding="utf-8") as f:
                        effective_psk = json.load(f).get("mesh_psk_hex")
                except Exception:
                    pass

        psk_bytes = bytes.fromhex(effective_psk.strip()) if effective_psk else None

        if os.path.exists(node_sec_dir) or psk_bytes:
            try:
                return NodeKeyring(
                    node_id=self.node_id,
                    passphrase=passphrase,
                    keys_dir=sec_dir,
                    mesh_key=psk_bytes,
                )
            except Exception as e:
                if self.strict_security:
                    raise StrictSecurityError(f"Strict security keyring initialization failed: {e}")
                print(f"[WARN] Keyring setup failed: {e}; running in unauthenticated mode.")
        elif self.strict_security:
            raise StrictSecurityError(f"Strict security enabled but no credentials found for '{self.node_id}'.")
        return None

    def _handle_new_event(self, event: Event) -> None:
        """Callback triggered whenever an event is logged locally or received from peers."""
        # A. If it is an attachment, ensure local disk persistence
        if event.entity_type == "attachment" and isinstance(event.payload, dict):
            try:
                self.attachment_mgr.ingest_attachment_event(event.payload)
            except Exception as e:
                print(f"[ATTACHMENT] Failed to ingest attachment: {e}")

        # B. Push real-time WebSocket state update to connected browsers
        if self.async_loop and self.async_loop.is_running():
            msg = {
                "type": "STATE_UPDATE",
                "node_id": self.node_id,
                "event": event.to_dict(),
                "state": self.node.get_state(),
                "version_vector": self.node.get_version_vector(),
                "timestamp": time.time(),
            }
            asyncio.run_coroutine_threadsafe(ws_broadcaster.broadcast(msg), self.async_loop)

    def _on_peer_discovered(self, peer_id: str, host: str, tcp_port: int, web_port: int) -> None:
        """Invoked when UDP beacon discovers a peer laptop on LAN."""
        print(f"\n[PEER DISCOVERY] Discovered '{peer_id}' at {host}:{tcp_port} (web: {web_port})")
        self.transport.add_peer(peer_id, host, tcp_port)
        self.gossip.add_peer(peer_id)
        # Immediate anti-entropy catchup
        self.gossip.wake_up()

    def _on_peer_lost(self, peer_id: str) -> None:
        """Invoked when peer heartbeat beacon times out."""
        print(f"\n[PEER MONITOR] Peer '{peer_id}' heartbeat lost (offline/out of range)")

    def add_manual_peer(self, peer_id: str, host: str, port: int) -> None:
        """Register a peer IP address manually."""
        self.transport.add_peer(peer_id, host, port)
        self.gossip.add_peer(peer_id)
        self.gossip.wake_up()

    def load_peers_file(self, file_path: str) -> int:
        """Load peer list from peer_ips.txt file if present."""
        if not os.path.exists(file_path):
            return 0
        loaded = 0
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" in line:
                        p_id, addr = line.split("=", 1)
                        if ":" in addr:
                            host, port_s = addr.split(":", 1)
                            self.add_manual_peer(p_id.strip(), host.strip(), int(port_s.strip()))
                            loaded += 1
        except Exception as e:
            print(f"[WARN] Error reading peer file '{file_path}': {e}")
        return loaded

    def close(self) -> None:
        """Clean shutdown of all node services."""
        if self.discovery:
            self.discovery.stop()
        self.gossip.stop()
        self.transport.close()
        self.node.close()


# -------------------------------------------------------------
# FASTAPI APPLICATION BUILDER
# -------------------------------------------------------------

def create_app(service: RescueNetNodeService) -> FastAPI:
    """Build FastAPI application bound to the local RescueNetNodeService."""
    app = FastAPI(
        title=f"RescueNet Node - {service.node_id}",
        description="Offline Disaster Coordination Network Node",
        version="2.0.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # -------------------------------------------------------------
    # LIFECYCLE HOOKS
    # -------------------------------------------------------------
    @app.on_event("startup")
    async def startup_event():
        service.async_loop = asyncio.get_running_loop()
        # Launch periodic telemetry broadcast task
        asyncio.create_task(telemetry_stream_worker())

    async def telemetry_stream_worker():
        """Periodically broadcasts telemetry to frontend every 1.5 seconds."""
        while True:
            try:
                await asyncio.sleep(1.5)
                # Compute telemetry snapshot
                state = service.node.get_state()
                vv = service.node.get_version_vector()
                ph = service.node.get_peer_health()
                stats = service.transport.get_stats()

                # Stations summary
                stations_data = {}
                for nid, prof in NODE_PROFILES.items():
                    is_self = (nid == service.node_id)
                    p_health = ph.get(nid, {})
                    is_online = True if is_self else (p_health.get("status") == "ONLINE")
                    stations_data[nid] = {
                        "id": nid,
                        "name": prof["name"],
                        "role": prof["role"],
                        "status": "ONLINE" if is_online else "OFFLINE",
                        "battery": 98.0 if is_self else (85.0 if is_online else 0.0),
                        "x_km": prof["x_km"],
                        "y_km": prof["y_km"],
                        "is_local_node": is_self,
                        "last_latency_ms": p_health.get("last_latency_ms", 0.0),
                    }

                msg = {
                    "type": "TELEMETRY_TICK",
                    "metrics": {
                        "local_node_id": service.node_id,
                        "events_total": service.node.store.count(),
                        "wire_bytes": stats.get("total_bytes", 0),
                        "wire_messages": stats.get("total_messages", 0),
                        "peers_online": sum(1 for p in ph.values() if p.get("status") == "ONLINE"),
                        "incidents_open": len([i for i in state.get("incident", {}).values() if i.get("status") != "RESOLVED"]),
                        "victims_count": len(state.get("victim", {})),
                        "alerts_critical": len([a for a in state.get("alert", {}).values() if a.get("severity") == "CRITICAL" and not a.get("resolved")]),
                    },
                    "stations": stations_data,
                    "version_vector": vv,
                    "peer_health": ph,
                }
                await ws_broadcaster.broadcast(msg)
            except asyncio.CancelledError:
                break
            except Exception:
                pass

    # -------------------------------------------------------------
    # WEBSOCKET ENDPOINTS
    # -------------------------------------------------------------
    @app.websocket("/ws")
    @app.websocket("/api/node/ws")
    async def websocket_endpoint(ws: WebSocket):
        await ws_broadcaster.connect(ws)
        # Send initial full state snapshot
        try:
            init_msg = {
                "type": "INIT_STATE",
                "node_id": service.node_id,
                "role": NODE_PROFILES.get(service.node_id, {}).get("role", "Node"),
                "state": service.node.get_state(),
                "version_vector": service.node.get_version_vector(),
                "peer_health": service.node.get_peer_health(),
                "timestamp": time.time(),
            }
            await ws.send_text(json.dumps(init_msg))
            while True:
                # Keep alive and handle any incoming client ping/command
                data = await ws.receive_text()
        except WebSocketDisconnect:
            await ws_broadcaster.disconnect(ws)
        except Exception:
            await ws_broadcaster.disconnect(ws)

    # -------------------------------------------------------------
    # NODE STATUS & TELEMETRY
    # -------------------------------------------------------------
    @app.get("/api/node/status")
    @app.get("/api/status")
    def get_node_status():
        prof = NODE_PROFILES.get(service.node_id, {})
        return {
            "node_id": service.node_id,
            "name": prof.get("name", service.node_id),
            "role": prof.get("role", "Disaster Coordination Node"),
            "local_ip": service.local_ip,
            "tcp_port": service.tcp_port,
            "web_port": service.web_port,
            "database": service.db_path,
            "events_count": service.node.store.count(),
            "version_vector": service.node.get_version_vector(),
            "peer_health": service.node.get_peer_health(),
            "peers": service.transport.peers,
            "wire_stats": service.transport.get_stats(),
            "strict_security": service.strict_security,
            "timestamp": time.time(),
        }

    @app.get("/api/node/state")
    def get_node_state():
        return service.node.get_state()

    @app.get("/api/stations")
    def get_stations():
        ph = service.node.get_peer_health()
        res = []
        for nid, prof in NODE_PROFILES.items():
            is_self = (nid == service.node_id)
            p_health = ph.get(nid, {})
            is_online = True if is_self else (p_health.get("status") == "ONLINE")
            peer_addr = service.transport.peers.get(nid)
            res.append({
                "id": nid,
                "node_id": nid,
                "name": prof["name"],
                "role": prof["role"],
                "description": prof["description"],
                "status": "ONLINE" if is_online else "OFFLINE",
                "x_km": prof["x_km"],
                "y_km": prof["y_km"],
                "coords": prof["coords"],
                "antenna_mast_m": prof["antenna_mast_m"],
                "battery": 98.0 if is_self else (85.0 if is_online else 0.0),
                "is_local_node": is_self,
                "ip": service.local_ip if is_self else (peer_addr[0] if peer_addr else None),
                "tcp_port": service.tcp_port if is_self else (peer_addr[1] if peer_addr else None),
                "last_latency_ms": p_health.get("last_latency_ms", 0.0),
            })
        return res

    @app.get("/api/topology")
    def get_topology():
        nodes = get_stations()
        links = []
        ph = service.node.get_peer_health()
        for nid, (p_host, p_port) in service.transport.peers.items():
            p_health = ph.get(nid, {})
            is_active = (p_health.get("status") == "ONLINE")
            links.append({
                "source": service.node_id,
                "target": nid,
                "active": is_active,
                "latency_ms": p_health.get("last_latency_ms", 5.0),
                "type": "TCP_DIRECT",
            })
        return {"nodes": nodes, "links": links}

    @app.get("/api/nodes")
    def get_nodes_list():
        st = service.node.get_state()
        vv = service.node.get_version_vector()
        ph = service.node.get_peer_health()
        res = []
        for nid, prof in NODE_PROFILES.items():
            res.append({
                "node_id": nid,
                "name": prof["name"],
                "role": prof["role"],
                "events_count": vv.get(nid, 0),
                "version_vector": vv,
                "peer_health": ph.get(nid, {}),
                "strict_mode": service.strict_security,
            })
        return res

    @app.get("/api/nodes/{nid}/state")
    def get_target_node_state(nid: str):
        return service.node.get_state()

    @app.get("/api/nodes/{nid}/events")
    def get_target_node_events(nid: str):
        all_events = service.node.store.get_all_events()
        return [e.to_dict() for e in all_events if e.node_id == nid or nid == "all"]

    @app.get("/api/metrics")
    def get_metrics():
        stats = service.transport.get_stats()
        state = service.node.get_state()
        ph = service.node.get_peer_health()
        return {
            "local_node_id": service.node_id,
            "events_total": service.node.store.count(),
            "wire_bytes": stats.get("total_bytes", 0),
            "wire_messages": stats.get("total_messages", 0),
            "peers_online": sum(1 for p in ph.values() if p.get("status") == "ONLINE"),
            "incidents_open": len([i for i in state.get("incident", {}).values() if i.get("status") != "RESOLVED"]),
            "victims_count": len(state.get("victim", {})),
            "rescuers_active": len([r for r in state.get("rescuer", {}).values() if r.get("status") in ("AVAILABLE", "DEPLOYED")]),
            "alerts_critical": len([a for a in state.get("alert", {}).values() if a.get("severity") == "CRITICAL" and not a.get("resolved")]),
            "version_vector": service.node.get_version_vector(),
        }

    # -------------------------------------------------------------
    # 1. INCIDENTS API
    # -------------------------------------------------------------
    @app.get("/api/node/incidents")
    @app.get("/api/incidents")
    def list_incidents():
        incidents = service.node.get_state().get("incident", {})
        return sorted(list(incidents.values()), key=lambda x: x.get("_created_at", 0), reverse=True)

    @app.post("/api/node/incidents")
    @app.post("/api/incidents")
    def create_incident(req: IncidentRequest):
        iid = req.incident_id or f"inc-{int(time.time()*1000)%1000000}"
        ev = service.node.record_event(
            entity_type="incident",
            entity_id=iid,
            operation="CREATE",
            payload={
                "title": req.title,
                "severity": req.severity,
                "location": req.location,
                "description": req.description,
                "status": "OPEN",
                "assigned_teams": req.assigned_teams,
            },
        )
        return {"status": "SUCCESS", "incident_id": iid, "event": ev.to_dict()}

    # -------------------------------------------------------------
    # 2. VICTIMS & TRIAGE API
    # -------------------------------------------------------------
    @app.get("/api/node/victims")
    @app.get("/api/victims")
    def list_victims():
        victims = service.node.get_state().get("victim", {})
        return sorted(list(victims.values()), key=lambda x: x.get("_created_at", 0), reverse=True)

    @app.post("/api/node/victims")
    @app.post("/api/victims")
    def record_victim(req: VictimRequest):
        vid = req.victim_id or f"vic-{int(time.time()*1000)%1000000}"
        ev = service.node.record_event(
            entity_type="victim",
            entity_id=vid,
            operation="CREATE",
            payload={
                "name": req.name,
                "triage_category": req.triage_category,
                "status": req.status,
                "medical_needs": req.medical_needs,
                "location": req.location,
                "contact_info": req.contact_info,
            },
        )
        return {"status": "SUCCESS", "victim_id": vid, "event": ev.to_dict()}

    # -------------------------------------------------------------
    # 3. RESCUERS API
    # -------------------------------------------------------------
    @app.get("/api/node/rescuers")
    @app.get("/api/rescuers")
    def list_rescuers():
        rescuers = service.node.get_state().get("rescuer", {})
        return list(rescuers.values())

    @app.post("/api/node/rescuers")
    @app.post("/api/rescuers")
    def record_rescuer(req: RescuerRequest):
        rid = req.rescuer_id or f"res-{int(time.time()*1000)%1000000}"
        ev = service.node.record_event(
            entity_type="rescuer",
            entity_id=rid,
            operation="CREATE",
            payload={
                "name": req.name,
                "role": req.role,
                "status": req.status,
                "team": req.team,
                "location": req.location,
                "callsign": req.callsign,
            },
        )
        return {"status": "SUCCESS", "rescuer_id": rid, "event": ev.to_dict()}

    # -------------------------------------------------------------
    # 4. SUPPLIES & NEEDS API
    # -------------------------------------------------------------
    @app.get("/api/node/supplies")
    @app.get("/api/supplies")
    def list_supplies():
        state = service.node.get_state()
        return {
            "supplies": list(state.get("supply", {}).values()),
            "needs": list(state.get("need", {}).values()),
            "pools": list(state.get("supply_intent", {}).values()),
        }

    @app.post("/api/node/supplies")
    @app.post("/api/supplies")
    def record_supply(req: SupplyRequest):
        sid = req.supply_id or f"sup-{int(time.time()*1000)%1000000}"
        etype = "need" if req.is_need else "supply"
        payload = {
            "item_name": req.item_name,
            "quantity": req.quantity,
            "unit": req.unit,
            "location": req.location,
            "urgency": req.urgency,
            "status": "OPEN",
        }
        if not req.is_need:
            payload["quotas"] = {service.node_id: req.quantity}

        ev = service.node.record_event(
            entity_type=etype,
            entity_id=sid,
            operation="CREATE",
            payload=payload,
        )
        return {"status": "SUCCESS", "entity_id": sid, "entity_type": etype, "event": ev.to_dict()}

    # -------------------------------------------------------------
    # 5. EMERGENCY ALERTS API
    # -------------------------------------------------------------
    @app.get("/api/node/alerts")
    @app.get("/api/alerts")
    def list_alerts():
        alerts = service.node.get_state().get("alert", {})
        return sorted(list(alerts.values()), key=lambda x: x.get("_created_at", 0), reverse=True)

    @app.post("/api/node/alerts")
    @app.post("/api/alerts")
    def create_alert(req: AlertRequest):
        aid = req.alert_id or f"alt-{int(time.time()*1000)%1000000}"
        ev = service.node.record_event(
            entity_type="alert",
            entity_id=aid,
            operation="CREATE",
            payload={
                "title": req.title,
                "message": req.message,
                "severity": req.severity,
                "source_node": service.node_id,
                "acknowledged": False,
                "resolved": False,
            },
        )
        return {"status": "SUCCESS", "alert_id": aid, "event": ev.to_dict()}

    @app.post("/api/node/alerts/{alert_id}/acknowledge")
    def acknowledge_alert(alert_id: str):
        ev = service.node.record_event(
            entity_type="alert",
            entity_id=alert_id,
            operation="ACKNOWLEDGE",
            payload={"acknowledged_by": service.node_id},
        )
        return {"status": "SUCCESS", "alert_id": alert_id, "event": ev.to_dict()}

    @app.post("/api/node/alerts/{alert_id}/resolve")
    def resolve_alert(alert_id: str):
        ev = service.node.record_event(
            entity_type="alert",
            entity_id=alert_id,
            operation="RESOLVE",
            payload={"resolved_by": service.node_id},
        )
        return {"status": "SUCCESS", "alert_id": alert_id, "event": ev.to_dict()}

    @app.post("/api/actions/sos")
    def action_sos(req: AlertRequest):
        """Broadcast emergency SOS."""
        return create_alert(req)

    # -------------------------------------------------------------
    # 6. FIELD CHAT API
    # -------------------------------------------------------------
    @app.get("/api/node/chat")
    @app.get("/api/chat")
    def list_chat(channel: Optional[str] = None):
        chats = service.node.get_state().get("chat", {})
        msg_list = list(chats.values())
        if channel:
            msg_list = [m for m in msg_list if m.get("channel") == channel]
        return sorted(msg_list, key=lambda x: x.get("_created_at", 0))

    @app.post("/api/node/chat")
    @app.post("/api/chat")
    def post_chat(req: ChatRequest):
        mid = req.message_id or f"msg-{int(time.time()*1000)%1000000}"
        prof = NODE_PROFILES.get(service.node_id, {})
        sender = req.sender_name or prof.get("name", service.node_id)
        ev = service.node.record_event(
            entity_type="chat",
            entity_id=mid,
            operation="CREATE",
            payload={
                "message_id": mid,
                "text": req.text,
                "channel": req.channel,
                "sender_id": service.node_id,
                "sender_name": sender,
            },
        )
        return {"status": "SUCCESS", "message_id": mid, "event": ev.to_dict()}

    # -------------------------------------------------------------
    # 7. OFFLINE ATTACHMENTS API
    # -------------------------------------------------------------
    @app.get("/api/node/attachments")
    @app.get("/api/attachments")
    def list_attachments():
        state_att = service.node.get_state().get("attachment", {})
        disk_att = service.attachment_mgr.list_attachments()
        return {"events": list(state_att.values()), "files": disk_att}

    @app.post("/api/node/attachments")
    @app.post("/api/attachments")
    async def upload_attachment(
        file: UploadFile = File(...),
        description: str = Form(""),
    ):
        content = await file.read()
        saved = service.attachment_mgr.save_file(
            filename=file.filename or "upload.bin",
            content=content,
            description=description,
            uploader=service.node_id,
        )
        # Log attachment event to mesh so peers automatically sync it
        ev = service.node.record_event(
            entity_type="attachment",
            entity_id=saved["file_id"],
            operation="CREATE",
            payload=saved,
        )
        return {"status": "SUCCESS", "attachment": saved, "event": ev.to_dict()}

    @app.get("/api/node/attachments/{file_id}/download")
    @app.get("/api/attachments/{file_id}/download")
    def download_attachment(file_id: str):
        found = service.attachment_mgr.get_attachment(file_id)
        if not found:
            raise HTTPException(status_code=404, detail="Attachment file not found on local disk")
        filepath, filename, mime_type = found
        return FileResponse(filepath, media_type=mime_type, filename=filename)

    # -------------------------------------------------------------
    # 8. MESH PEERS & MANUAL SYNC API
    # -------------------------------------------------------------
    @app.post("/api/node/peers")
    def add_peer(req: AddPeerRequest):
        service.add_manual_peer(req.peer_id, req.host, req.port)
        return {
            "status": "PEER_ADDED",
            "peer_id": req.peer_id,
            "host": req.host,
            "port": req.port,
            "all_peers": service.transport.peers,
        }

    @app.post("/api/node/sync")
    @app.post("/api/actions/sync")
    def trigger_mesh_sync(source_id: Optional[str] = None, target_id: Optional[str] = None):
        """Run immediate anti-entropy sync against one or all peers."""
        if target_id:
            stats = service.node.sync_with(target_id)
            return {"status": "SYNC_COMPLETE", "results": [stats.to_dict()]}
        else:
            stats_list = service.gossip.trigger_now()
            return {"status": "SYNC_COMPLETE", "results": [s.to_dict() for s in stats_list]}

    @app.post("/api/actions/event")
    def record_generic_event(req: GenericEventRequest):
        ev = service.node.record_event(
            entity_type=req.entity_type,
            entity_id=req.entity_id,
            operation=req.operation,
            payload=req.payload,
        )
        return {"status": "EVENT_RECORDED", "event_id": ev.event_id, "counter": ev.counter}

    # -------------------------------------------------------------
    # 9. STATIC FRONTEND ASSETS
    # -------------------------------------------------------------
    if os.path.isdir(service.static_dir):
        app.mount("/", StaticFiles(directory=service.static_dir, html=True), name="static")

    return app


# -------------------------------------------------------------
# MAIN CLI ENTRYPOINT
# -------------------------------------------------------------

def parse_args():
    parser = argparse.ArgumentParser(description="RescueNet Unified Node & Dashboard Server")
    parser.add_argument("--node-id", required=True, help="Unique node identifier (alpha-harbor, beta-hospital, gamma-mountain)")
    parser.add_argument("--host", default="0.0.0.0", help="Host interface to bind (0.0.0.0 for LAN)")
    parser.add_argument("--tcp-port", type=int, default=8001, help="TCP port for mesh synchronization (default 8001)")
    parser.add_argument("--web-port", type=int, default=8000, help="Web/API HTTP port (default 8000)")
    parser.add_argument("--db", default="", help="SQLite database path (default data/<node_id>.db)")
    parser.add_argument("--security-dir", default="", help="Security credentials directory")
    parser.add_argument("--mesh-psk", default="", help="256-bit Mesh Pre-Shared Key (64 hex characters)")
    parser.add_argument("--passphrase", default="", help="Passphrase for node private key decryption")
    parser.add_argument("--strict-security", action="store_true", help="Enforce strict production zero-trust security")
    parser.add_argument("--no-discovery", action="store_true", help="Disable UDP peer discovery beacon")
    parser.add_argument("--discovery-port", type=int, default=8002, help="UDP peer discovery port (default 8002)")
    parser.add_argument("--peers", default="", help="Comma-separated manual peers: 'beta-hospital=192.168.1.102:8001'")
    parser.add_argument("--peer-file", default="peer_ips.txt", help="Path to peer configuration file (default peer_ips.txt)")
    return parser.parse_args()


def main():
    args = parse_args()

    service = RescueNetNodeService(
        node_id=args.node_id,
        host=args.host,
        tcp_port=args.tcp_port,
        web_port=args.web_port,
        db_path=args.db if args.db else None,
        security_dir=args.security_dir if args.security_dir else None,
        mesh_psk_hex=args.mesh_psk if args.mesh_psk else None,
        passphrase=args.passphrase if args.passphrase else None,
        strict_security=args.strict_security,
        enable_discovery=not args.no_discovery,
        discovery_port=args.discovery_port,
    )

    # Load CLI peers
    if args.peers:
        for item in args.peers.split(","):
            if "=" in item:
                pid, addr = item.split("=", 1)
                if ":" in addr:
                    h, p = addr.split(":", 1)
                    service.add_manual_peer(pid.strip(), h.strip(), int(p.strip()))

    # Load peer file
    if args.peer_file:
        service.load_peers_file(args.peer_file)

    app = create_app(service)

    print("\n" + "=" * 75)
    print(f" RESCUENET OFFLINE NODE SERVER: {service.node_id.upper()}")
    print("=" * 75)
    print(f"  * Node Identity:       {service.node_id}")
    print(f"  * Local IPv4:          {service.local_ip}")
    print(f"  * TCP Sync Port:       {service.tcp_port} (framed delta sync)")
    print(f"  * UDP Discovery Port:  {service.discovery_port} (auto beacon)")
    print(f"  * Web Dashboard URL:   http://{service.local_ip}:{service.web_port}/")
    print(f"  * Database:            {service.db_path}")
    print(f"  * Strict Security:     {service.strict_security}")
    print(f"  * Registered Peers:    {list(service.transport.peers.keys())}")
    print("=" * 75 + "\n")

    try:
        uvicorn.run(app, host=args.host, port=args.web_port, log_level="info")
    except KeyboardInterrupt:
        pass
    finally:
        print("\nShutting down node service...")
        service.close()


if __name__ == "__main__":
    main()
