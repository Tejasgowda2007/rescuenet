"""
Integration Tests for RescueNet FastAPI Node Server Endpoints.
Verifies REST APIs and WebSocket communication for live dashboard integration.
"""

import os
import tempfile
import pytest
from starlette.testclient import TestClient

from api.node_server import RescueNetNodeService, create_app
from auth.database import init_admin_account, get_user_by_username, update_user_password


TEST_MESH_KEY = bytes.fromhex("16338ae4f5da5340c4495a0083065aa94c69aa7a1ff4d63e175f43401ac16d69")
SECURITY_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "security"))


@pytest.fixture
def test_node_service(tmp_path):
    db_file = str(tmp_path / "test_node.db")
    att_dir = str(tmp_path / "attachments")
    service = RescueNetNodeService(
        node_id="alpha-harbor",
        host="127.0.0.1",
        tcp_port=0,
        web_port=0,
        db_path=db_file,
        security_dir=SECURITY_DIR,
        mesh_psk_hex="16338ae4f5da5340c4495a0083065aa94c69aa7a1ff4d63e175f43401ac16d69",
        strict_security=True,
        enable_discovery=False,
        attachments_dir=att_dir,
    )
    yield service
    service.close()


def test_node_server_rest_endpoints(test_node_service):
    app = create_app(test_node_service)
    client = TestClient(app)

    # 1. Status endpoint (Public health check)
    res_status = client.get("/api/node/status")
    assert res_status.status_code == 200
    data = res_status.json()
    assert data["node_id"] == "alpha-harbor"
    assert data["strict_security"] is True

    # 1b. Verify unauthenticated access to protected endpoint is rejected with 401
    res_unauth = client.get("/api/node/incidents")
    assert res_unauth.status_code == 401
    assert "detail" in res_unauth.json()

    # 1c. Authenticate operator session
    os.environ["RESCUENET_ADMIN_USER"] = "admin"
    os.environ["RESCUENET_ADMIN_PASSWORD"] = "Rnet!Admin2026"
    init_admin_account()
    u = get_user_by_username("admin")
    if u:
        update_user_password(u["id"], "Rnet!Admin2026")

    login_res = client.post("/api/auth/login", json={"username": "admin", "password": "Rnet!Admin2026"})
    assert login_res.status_code == 200
    token = login_res.json()["access_token"]
    client.headers = {"Authorization": f"Bearer {token}"}

    # 2. Incident creation & listing
    res_inc = client.post("/api/node/incidents", json={
        "title": "Severe Levee Breach",
        "severity": "CRITICAL",
        "location": "Sector 9",
        "description": "Evacuate low lying areas immediately",
    })
    assert res_inc.status_code == 200
    assert res_inc.json()["status"] == "SUCCESS"

    res_inc_list = client.get("/api/node/incidents")
    assert res_inc_list.status_code == 200
    assert len(res_inc_list.json()) == 1
    assert res_inc_list.json()[0]["title"] == "Severe Levee Breach"

    # 3. Victim triage & listing
    res_vic = client.post("/api/node/victims", json={
        "name": "Jane Doe",
        "triage_category": "RED",
        "status": "CRITICAL_INJURY",
        "medical_needs": "Immediate blood transfusion",
        "location": "Harbor Pier 2",
    })
    assert res_vic.status_code == 200
    res_vic_list = client.get("/api/node/victims")
    assert len(res_vic_list.json()) == 1
    assert res_vic_list.json()[0]["name"] == "Jane Doe"

    # 4. Rescuers
    res_res = client.post("/api/node/rescuers", json={
        "name": "Rescue Squad Alpha",
        "role": "Paramedic",
        "status": "DEPLOYED",
    })
    assert res_res.status_code == 200
    res_res_list = client.get("/api/node/rescuers")
    assert len(res_res_list.json()) == 1

    # 5. Emergency Alerts
    res_alt = client.post("/api/node/alerts", json={
        "title": "Tsunami Warning",
        "message": "Move to higher ground immediately",
        "severity": "CRITICAL",
    })
    assert res_alt.status_code == 200
    alert_id = res_alt.json()["alert_id"]

    res_ack = client.post(f"/api/node/alerts/{alert_id}/acknowledge")
    assert res_ack.status_code == 200

    # 6. Field Chat
    res_chat = client.post("/api/node/chat", json={
        "text": "Medical teams in position at harbor perimeter.",
        "channel": "medical",
    })
    assert res_chat.status_code == 200
    res_chat_list = client.get("/api/node/chat?channel=medical")
    assert len(res_chat_list.json()) == 1

    # 7. Attachment upload and download
    dummy_file = b"RESCUENET-SAMPLE-OFFLINE-MAP-PNG-DATA"
    res_upload = client.post(
        "/api/node/attachments",
        files={"file": ("evac_map.png", dummy_file, "image/png")},
        data={"description": "Evacuation Route Plan"},
    )
    assert res_upload.status_code == 200
    file_id = res_upload.json()["attachment"]["file_id"]

    res_download = client.get(f"/api/node/attachments/{file_id}/download")
    assert res_download.status_code == 200
    assert res_download.content == dummy_file

    # 8. Stations, Topology, and Metrics compatibility endpoints
    res_stn = client.get("/api/stations")
    assert res_stn.status_code == 200
    assert len(res_stn.json()) == 3

    res_top = client.get("/api/topology")
    assert res_top.status_code == 200

    res_met = client.get("/api/metrics")
    assert res_met.status_code == 200
    assert res_met.json()["events_total"] >= 5
