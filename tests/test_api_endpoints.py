"""
Unit and Integration Tests for Functional Backend REST API Endpoints.
"""

from __future__ import annotations
import functools
import threading
import pytest
from api.server import (
    state,
    list_nodes,
    sync_node_endpoint,
    list_incidents,
    create_incident_endpoint,
    update_incident_status_endpoint,
    list_victims,
    register_victim_endpoint,
    update_victim_triage_endpoint,
    list_shelters,
    create_shelter_endpoint,
    update_shelter_occupancy_endpoint,
    get_resources,
    create_resource_pool_endpoint,
    consume_resource_endpoint,
    transfer_quota_endpoint,
    register_scarce_token_endpoint,
    request_scarce_token_endpoint,
    confirm_scarce_token_endpoint,
    query_events_endpoint,
    get_security_peers,
    get_security_audit_logs,
    IncidentCreateRequest,
    IncidentStatusRequest,
    VictimCreateRequest,
    VictimTriageRequest,
    ShelterCreateRequest,
    ShelterOccupancyRequest,
    SupplyPoolCreateRequest,
    SupplyConsumeRequest,
    SupplyTransferQuotaRequest,
    ScarceTokenRegisterRequest,
    ScarceTokenRequestAction,
    ScarceTokenConfirmAction,
)


def timed_test(timeout_sec: float = 10.0):
    """Enforce a strict timeout on test execution to prevent indefinite hangs."""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            err = []
            def target():
                try:
                    func(*args, **kwargs)
                except BaseException as e:
                    err.append(e)

            t = threading.Thread(target=target, daemon=True)
            t.start()
            t.join(timeout=timeout_sec)
            if t.is_alive():
                raise TimeoutError(f"Test '{func.__name__}' exceeded strict timeout of {timeout_sec}s")
            if err:
                raise err[0]
        return wrapper
    return decorator


@timed_test(timeout_sec=10.0)
def test_list_nodes_endpoint():
    nodes = list_nodes()
    assert isinstance(nodes, list)
    assert len(nodes) == 5
    node_ids = [n["node_id"] for n in nodes]
    assert "alpha" in node_ids
    assert "bravo" in node_ids
    assert "charlie" in node_ids
    assert "delta" in node_ids
    assert "echo" in node_ids

    alpha = next(n for n in nodes if n["node_id"] == "alpha")
    assert "version_vector" in alpha
    assert "has_gaps" in alpha
    assert alpha["has_gaps"] is False
    assert "battery_pct" in alpha
    assert "coords" in alpha


@timed_test(timeout_sec=10.0)
def test_incident_api_lifecycle():
    # 1. Create incident
    req = IncidentCreateRequest(
        node_id="alpha",
        incident_id="inc-api-1",
        title="Wildfire Sector East",
        severity="CRITICAL",
        location="Grid K-4",
        description="Fast moving brush fire approaching communications relay",
        assigned_teams=["Hotshot Crew 1"],
    )
    res = create_incident_endpoint(req)
    assert res["status"] == "INCIDENT_CREATED"
    assert res["incident_id"] == "inc-api-1"

    # 2. List incidents
    incidents = list_incidents(node_id="alpha")
    inc = next(i for i in incidents if i["entity_id"] == "inc-api-1")
    assert inc["title"] == "Wildfire Sector East"
    assert inc["severity"] == "CRITICAL"
    assert "Hotshot Crew 1" in inc["assigned_teams"]
    assert inc["status"] == "OPEN"

    # 3. Assign second team
    assign_req = IncidentStatusRequest(
        node_id="alpha",
        assign_team="Aerial Tanker 3",
    )
    res_assign = update_incident_status_endpoint("inc-api-1", assign_req)
    assert res_assign["status"] == "TEAM_ASSIGNED"

    # 4. Resolve incident
    resolve_req = IncidentStatusRequest(
        node_id="alpha",
        status="RESOLVED",
        resolution_notes="Fire contained with retardant drops, relay secured",
    )
    res_resolve = update_incident_status_endpoint("inc-api-1", resolve_req)
    assert res_resolve["status"] == "INCIDENT_RESOLVED"

    # Verify resolved status
    incidents_after = list_incidents(node_id="alpha")
    inc_resolved = next(i for i in incidents_after if i["entity_id"] == "inc-api-1")
    assert inc_resolved["status"] == "RESOLVED"
    assert "Aerial Tanker 3" in inc_resolved["assigned_teams"]


@timed_test(timeout_sec=10.0)
def test_victim_triage_api_lifecycle():
    # 1. Register victim
    req = VictimCreateRequest(
        node_id="alpha",
        victim_id="vic-api-1",
        name="Elena Rostova",
        triage_category="RED",
        status="CRITICAL",
        medical_needs="Inhalation injury, severe burns",
        location="Sector East Ranger Station",
        contact_info="Emergency Contact: 555-0144",
    )
    res = register_victim_endpoint(req)
    assert res["status"] == "VICTIM_REGISTERED"

    # 2. List victims
    victims = list_victims(node_id="alpha")
    vic = next(v for v in victims if v["entity_id"] == "vic-api-1")
    assert vic["name"] == "Elena Rostova"
    assert vic["triage_category"] == "RED"

    # 3. Update triage to YELLOW after field treatment
    update_req = VictimTriageRequest(
        node_id="alpha",
        triage_category="YELLOW",
        status="STABILIZED",
        medical_needs="Oxygen administered, vitals stable",
    )
    res_update = update_victim_triage_endpoint("vic-api-1", update_req)
    assert res_update["status"] == "TRIAGE_UPDATED"

    # Verify updated record
    victims_after = list_victims(node_id="alpha")
    vic_after = next(v for v in victims_after if v["entity_id"] == "vic-api-1")
    assert vic_after["triage_category"] == "YELLOW"
    assert vic_after["status"] == "STABILIZED"


@timed_test(timeout_sec=10.0)
def test_shelter_api_lifecycle():
    # 1. Create shelter
    req = ShelterCreateRequest(
        node_id="alpha",
        shelter_id="sh-api-1",
        name="Central High School Gym",
        capacity=200,
        location="Zone 1",
    )
    res_create = create_shelter_endpoint(req)
    assert res_create["status"] == "SHELTER_CREATED"

    # 2. Update occupancy
    occ_req = ShelterOccupancyRequest(node_id="alpha", occupancy=85)
    res_occ = update_shelter_occupancy_endpoint("sh-api-1", occ_req)
    assert res_occ["status"] == "OCCUPANCY_UPDATED"
    assert res_occ["occupancy"] == 85

    # 3. List shelters
    shelters = list_shelters(node_id="alpha")
    sh = next(s for s in shelters if s["entity_id"] == "sh-api-1")
    assert sh["name"] == "Central High School Gym"
    assert sh["capacity"] == 200
    assert sh["occupancy"] == 85


@timed_test(timeout_sec=10.0)
def test_resources_and_escrow_api():
    # 1. Create supply pool
    pool_req = SupplyPoolCreateRequest(
        node_id="alpha",
        supply_id="water-rations-pool",
        item_name="Clean Drinking Water Pallets",
        total_quantity=100,
        initial_quotas={"alpha": 50, "bravo": 30, "charlie": 20},
        unit="pallets",
    )
    res_pool = create_resource_pool_endpoint(pool_req)
    assert res_pool["status"] == "POOL_CREATED"

    # 2. Consume from alpha's quota
    consume_req = SupplyConsumeRequest(
        node_id="alpha",
        supply_id="water-rations-pool",
        quantity=15,
        beneficiary="Field Triage Center",
        notes="Urgent hydration for burn victims",
    )
    res_consume = consume_resource_endpoint(consume_req)
    assert res_consume["status"] == "SUPPLY_CONSUMED"
    assert res_consume["quantity"] == 15

    # 3. Transfer quota: alpha -> bravo (10 pallets)
    xfer_req = SupplyTransferQuotaRequest(
        from_node_id="alpha",
        to_node_id="bravo",
        supply_id="water-rations-pool",
        quantity=10,
    )
    res_xfer = transfer_quota_endpoint(xfer_req)
    assert res_xfer["status"] == "QUOTA_TRANSFERRED"

    # 4. Query resources
    res_data = get_resources(node_id="alpha")
    assert "water-rations-pool" in res_data["supplies"]
    pool = res_data["supplies"]["water-rations-pool"]
    # Alpha started with 50, consumed 15, transferred 10 -> remaining 25
    assert pool["quotas"]["alpha"] == 25
    assert pool["quotas"]["bravo"] == 40
    assert pool["consumed"] == 15


@timed_test(timeout_sec=10.0)
def test_scarce_tokens_api():
    # 1. Register scarce boat token on alpha
    reg_req = ScarceTokenRegisterRequest(
        node_id="alpha",
        item_id="rescue-boat-1",
        item_name="Zodiac Inflatable Boat",
        initial_holder_id="alpha",
        category="maritime",
    )
    res_reg = register_scarce_token_endpoint(reg_req)
    assert res_reg["status"] == "TOKEN_REGISTERED"

    # 2. Bravo requests allocation
    req_req = ScarceTokenRequestAction(
        node_id="bravo",
        item_id="rescue-boat-1",
        mission="Evacuate flooded elderly home",
        urgency="CRITICAL",
    )
    res_req = request_scarce_token_endpoint(req_req)
    assert res_req["status"] == "ALLOCATION_REQUESTED"

    # 3. Alpha confirms allocation to Bravo
    confirm_req = ScarceTokenConfirmAction(
        node_id="alpha",
        item_id="rescue-boat-1",
        target_node_id="bravo",
        mission="Elderly Home Evacuation",
    )
    res_confirm = confirm_scarce_token_endpoint(confirm_req)
    assert res_confirm["status"] == "ALLOCATION_CONFIRMED"

    # Verify scarce item state
    res_data = get_resources(node_id="alpha")
    boat = res_data["scarce_items"]["rescue-boat-1"]
    assert boat["status"] == "CONFIRMED_ALLOCATED"
    assert boat["target_node"] == "bravo"


@timed_test(timeout_sec=10.0)
def test_events_pagination_endpoint():
    res = query_events_endpoint(node_id="alpha", limit=10, offset=0)
    assert "events" in res
    assert "total" in res
    assert res["total"] > 0
    assert len(res["events"]) <= 10
    assert res["node_id"] == "alpha"


@timed_test(timeout_sec=10.0)
def test_security_endpoints():
    peers = get_security_peers(node_id="alpha")
    assert "node_id" in peers
    assert peers["node_id"] == "alpha"

    audit_logs = get_security_audit_logs()
    assert isinstance(audit_logs, list)


@timed_test(timeout_sec=10.0)
def test_node_sync_endpoint():
    res = sync_node_endpoint(node_id="alpha", target_id="bravo")
    assert res["status"] == "SYNC_COMPLETE"
    assert len(res["results"]) == 1
    assert res["results"][0]["peer"] == "bravo"
