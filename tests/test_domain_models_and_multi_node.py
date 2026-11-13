"""
Tests for Extended Domain Models (Incidents, Victims, Triage) and MultiNodeManager.
"""

from __future__ import annotations
import pytest
from sync.multi_node_manager import MultiNodeManager
from events.event import Event
from storage.projector import StateProjector
from validation.schema import validate_event, ValidationError


def test_schema_validates_new_entities():
    # Valid incident
    ev_inc = Event("alpha", 1, 10.0, "incident", "inc-1", "CREATE", {"title": "Landslide Route 9", "severity": "HIGH"})
    validate_event(ev_inc)

    # Valid victim
    ev_vic = Event("alpha", 2, 20.0, "victim", "vic-1", "CREATE", {"name": "Jane Doe", "triage_category": "RED"})
    validate_event(ev_vic)

    # Invalid operation on victim
    ev_bad_op = Event("alpha", 3, 30.0, "victim", "vic-1", "EXPLODE", {"name": "Jane"})
    with pytest.raises(ValidationError):
        validate_event(ev_bad_op)


def test_incident_lifecycle_and_projection():
    projector = StateProjector()
    events = [
        Event("alpha", 1, 10.0, "incident", "inc-1", "CREATE", {
            "title": "Bridge Collapse",
            "severity": "CRITICAL",
            "location": "North River Crossing",
            "status": "OPEN",
            "assigned_teams": ["Team Alpha"],
        }),
        Event("alpha", 2, 20.0, "incident", "inc-1", "ASSIGN_TEAM", {
            "team": "Dive Rescue 2",
        }),
        Event("alpha", 3, 30.0, "incident", "inc-1", "CLOSE_INCIDENT", {
            "resolution_notes": "Bridge cleared, survivors transported to Base Alpha",
        }),
    ]

    state = projector.compute_state(events)
    inc = state["incident"]["inc-1"]
    assert inc["title"] == "Bridge Collapse"
    assert inc["severity"] == "CRITICAL"
    assert "Team Alpha" in inc["assigned_teams"]
    assert "Dive Rescue 2" in inc["assigned_teams"]
    assert inc["status"] == "RESOLVED"
    assert inc["_resolved_by"] == "alpha"
    assert inc["_resolution_notes"] == "Bridge cleared, survivors transported to Base Alpha"


def test_victim_triage_conflict_retention():
    projector = StateProjector()
    events = [
        Event("alpha", 1, 10.0, "victim", "vic-1", "CREATE", {
            "name": "Carlos M.",
            "triage_category": "YELLOW",
            "status": "INJURED",
            "location": "Sector 3",
        }),
        # Node Beta concurrently reports patient is in RED (critical) triage
        Event("beta", 1, 15.0, "victim", "vic-1", "UPDATE_TRIAGE", {
            "triage_category": "RED",
            "status": "CRITICAL",
            "medical_needs": "Severe bleeding",
        }),
    ]

    state = projector.compute_state(events)
    vic = state["victim"]["vic-1"]
    assert vic["name"] == "Carlos M."
    # Both conflict entries preserved
    assert len(vic["conflicts"]) >= 1
    conflict = vic["conflicts"][0]
    assert conflict["node_id"] == "beta"
    assert conflict["conflicting_triage"] == "RED"
    assert conflict["previous_triage"] == "YELLOW"


def test_multi_node_manager_end_to_end():
    manager = MultiNodeManager(auto_start_gossip=False)
    alpha = manager.add_node("alpha")
    beta = manager.add_node("beta")
    gamma = manager.add_node("gamma")

    # 1. Alpha creates incident
    manager.create_incident("alpha", "inc-101", "Mountain Pass Flood", severity="CRITICAL", location="Mile 14")
    # 2. Beta registers victim
    manager.register_victim("beta", "vic-202", "Alex R.", triage_category="RED", medical_needs="Oxygen required")
    # 3. Alpha creates supply pool and scarce boat token
    manager.create_supply_pool("alpha", "water-pool", "Bottled Water", total_quantity=100, initial_quotas={"alpha": 50, "beta": 30, "gamma": 20})
    manager.register_scarce_token("alpha", "boat-1", "Inflatable Rescue Boat", initial_holder_id="alpha")

    # Sync baseline inventory to Beta and Gamma
    manager.sync_all()

    # 4. Beta consumes 10 from its offline quota
    manager.consume_supply("beta", "water-pool", quantity=10, beneficiary="Evacuees at Field Hospital")
    # 5. Gamma requests boat allocation; Alpha confirms allocation to Gamma
    manager.request_scarce_token("gamma", "boat-1", mission="Rescue stranded family on island")
    manager.sync_pair("gamma", "alpha")
    manager.confirm_scarce_token("alpha", "boat-1", target_node_id="gamma", mission="Island Evacuation")

    # Sync all nodes to full convergence
    manager.sync_all()

    # Verify all 3 nodes have converged to the identical state
    state_alpha = alpha.get_state()
    state_beta = beta.get_state()
    state_gamma = gamma.get_state()

    # Incident present everywhere
    assert "inc-101" in state_alpha["incident"]
    assert "inc-101" in state_beta["incident"]
    assert "inc-101" in state_gamma["incident"]

    # Victim present everywhere
    assert "vic-202" in state_alpha["victim"]
    assert "vic-202" in state_beta["victim"]
    assert "vic-202" in state_gamma["victim"]

    # Supply quota conservation: Beta spent 10, now has 20. Total consumed is 10.
    supply_gamma = state_gamma["supply"]["water-pool"]
    assert supply_gamma["quotas"]["beta"] == 20
    assert supply_gamma["consumed"] == 10
    total_remaining = sum(supply_gamma["quotas"].values())
    assert total_remaining + supply_gamma["consumed"] == 100

    # Boat token confirmed allocation to Gamma
    boat_beta = state_beta["scarce_item"]["boat-1"]
    assert boat_beta["status"] == "CONFIRMED_ALLOCATED"
    assert boat_beta["target_node"] == "gamma"

    manager.close()
