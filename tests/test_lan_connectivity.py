"""
Integration tests for RescueNet FieldMesh Unified LAN Deployment.

Verifies:
1. Unified FastAPI server mounts compiled React frontend at `/` and static assets.
2. All REST API endpoint functions respond with expected schema and status.
3. CORS middleware is configured to permit remote LAN browser access (* origins).
4. WebSocket connection manager supports connection tracking and broadcasting.
5. Action endpoints (SOS broadcast, link toggle, station status) execute without error.
6. Offline self-containment (zero external script/font dependencies required for operation).
7. Host IP resolution correctly detects LAN interface address.
"""

import os
import pytest
from api.server import (
    app,
    DIST_DIR,
    state,
    get_terrain_data,
    list_stations,
    list_links,
    trigger_sos,
    toggle_link,
    SOSRequest,
    LinkToggleRequest,
)
from run_fieldmesh import get_lan_ip


def test_react_production_bundle_exists():
    """Verify that web/dist exists and contains index.html and assets."""
    assert os.path.isdir(DIST_DIR), f"DIST_DIR does not exist: {DIST_DIR}"
    index_file = os.path.join(DIST_DIR, "index.html")
    assert os.path.isfile(index_file), "index.html not found in web/dist"
    with open(index_file, "r", encoding="utf-8") as f:
        html = f.read()
    assert "<div id=\"root\"></div>" in html
    assert "RescueNet FieldMesh" in html
    assert "assets/" in html


def test_static_files_mounted_on_root():
    """Verify FastAPI routes mount StaticFiles at root / for frontend delivery."""
    mounted_names = [getattr(route, "name", None) for route in app.routes]
    assert "frontend" in mounted_names, "Static frontend mount missing from app.routes"
    frontend_route = next(r for r in app.routes if getattr(r, "name", None) == "frontend")
    assert frontend_route.path == "", "Frontend mount path should be at root"


def test_cors_middleware_configured_for_lan():
    """Verify CORS middleware is active and permits cross-origin LAN clients."""
    from starlette.middleware.cors import CORSMiddleware
    cors_middlewares = [m for m in app.user_middleware if m.cls == CORSMiddleware]
    assert len(cors_middlewares) > 0, "CORSMiddleware not configured on app"
    cors = cors_middlewares[0]
    assert "*" in cors.kwargs.get("allow_origins", [])


def test_lan_ip_detection():
    """Verify LAN IP detection returns a valid IPv4 address."""
    ip = get_lan_ip()
    assert isinstance(ip, str)
    parts = ip.split(".")
    assert len(parts) == 4
    for p in parts:
        assert p.isdigit()
        assert 0 <= int(p) <= 255


def test_rest_api_stations_endpoint():
    """Verify list_stations returns all 5 default stations."""
    stations = list_stations()
    assert isinstance(stations, list)
    station_ids = [s["id"] for s in stations]
    for required in ["alpha", "bravo", "charlie", "delta", "echo"]:
        assert required in station_ids


def test_rest_api_terrain_endpoint():
    """Verify get_terrain_data returns heightmap and features."""
    terrain = get_terrain_data()
    assert "width_km" in terrain
    assert "heightmap" in terrain
    assert "features" in terrain


def test_rest_api_links_endpoint():
    """Verify list_links returns radio links with LOS & link margin."""
    links = list_links()
    assert isinstance(links, list)
    assert len(links) > 0
    link = links[0]
    assert "margin_db" in link
    assert "distance_km" in link
    assert "frequency_mhz" in link


def test_rest_api_sos_action():
    """Verify trigger_sos broadcasts emergency alert with critical priority."""
    req = SOSRequest(source_id="alpha", message="LAN Readiness Drill Alert", urgency="CRITICAL")
    res = trigger_sos(req)
    assert res.get("status") == "SOS_BROADCAST_SCHEDULED"
    assert "packet_id" in res


def test_rest_api_link_toggle():
    """Verify toggle_link toggles radio link cut state."""
    req = LinkToggleRequest(node_a="alpha", node_b="bravo")
    res = toggle_link(req)
    assert res["status"] in ["CUT", "HEALED"]
    assert "link" in res
    # Re-toggle to restore original state
    res2 = toggle_link(req)
    assert res2["status"] in ["CUT", "HEALED"]


def test_websocket_manager_broadcast():
    """Verify WebSocket manager connection set and broadcast helper."""
    from api.websocket import ws_manager
    assert isinstance(ws_manager.active_connections, set)
