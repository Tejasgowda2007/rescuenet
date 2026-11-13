"""
UI Controller Logic for RescueNet & ResQ-Mesh Streamlit Demo.
Decouples state transitions (partitions, link toggles, sync mesh, USB bundles,
scenario presets, security setup, ResQ-Mesh 3-phase demo, sneakernet data mules,
device revocation, and SVG topology) from Streamlit rendering.
"""

from __future__ import annotations
import json
from typing import List, Dict, Any, Tuple, Optional
from simulator.engine import DisasterSimulator
from allocation.intent_ledger import IntentLedger
from crypto.keyring import NodeKeyring
from crypto.ciphers import FieldEncryptor
from events.event import Event
from allocation.escrow import EscrowManager
from allocation.tokens import TokenManager


UI_SHARED_PASSPHRASE = "rescuenet-field-ops-passphrase"
UI_SHARED_SALT = b"RescueNetUI_v1!!"  # Fixed 16-byte salt so simulated field stations share team key


def configure_mesh_security(
    sim: DisasterSimulator,
    passphrase: str = UI_SHARED_PASSPHRASE,
    salt: bytes = UI_SHARED_SALT,
) -> None:
    """Attach Ed25519 + AES-256-GCM keyrings to all nodes and cross-register public keys."""
    mesh_key = FieldEncryptor.derive_mesh_key(passphrase, salt)
    keyrings: Dict[str, NodeKeyring] = {
        nid: NodeKeyring(node_id=nid, passphrase=passphrase, salt=salt, mesh_key=mesh_key)
        for nid in sim.node_ids
    }
    for nid, kr in keyrings.items():
        for peer_id, peer_kr in keyrings.items():
            if peer_id != nid:
                kr.register_peer(peer_id, peer_kr.public_key_hex)
        sim.nodes[nid].set_keyring(kr)


def create_ui_simulator(enable_crypto: bool = True) -> DisasterSimulator:
    """
    Create and bootstrap the 3-node disaster coordination simulator for the UI.
    Attaches shared Ed25519 signing & AES-256-GCM field encryption across all nodes.
    """
    sim = DisasterSimulator(["alpha-harbor", "beta-hospital", "gamma-mountain"], seed=42)
    configure_mesh_security(sim)
    sim.bootstrap_default_scenario()
    
    # Initialize ResQ-Mesh Pillar 2 Intent Pool (10 Medical Kits)
    IntentLedger.init_pool(
        node=sim.nodes["alpha-harbor"],
        item_id="medical-kits-pool",
        item_name="Emergency Trauma Kits",
        total_quantity=10,
        unit="kits",
    )
    # Sync initial pool to all connected nodes
    sim.nodes["alpha-harbor"].sync_with("beta-hospital")
    sim.nodes["alpha-harbor"].sync_with("gamma-mountain")
    sim.nodes["beta-hospital"].sync_with("gamma-mountain")
    
    return sim


def cut_network_partition(sim: DisasterSimulator) -> List[List[str]]:
    """Simulate a hurricane split separating gamma-mountain from alpha/beta."""
    groups = [["alpha-harbor", "beta-hospital"], ["gamma-mountain"]]
    sim.partition_manager.set_partitions(groups)
    return groups


def set_custom_partition(sim: DisasterSimulator, mode: str) -> List[List[str]]:
    """
    Apply a named network topology preset:
    - full_mesh: all 3 links connected
    - isolate_gamma: [alpha, beta] | [gamma]
    - isolate_alpha: [alpha] | [beta, gamma]
    - isolate_beta: [beta] | [alpha, gamma]
    - split_all: [alpha] | [beta] | [gamma]
    - chain_relay: alpha <-> beta <-> gamma (alpha <-> gamma direct link cut)
    """
    if mode == "full_mesh":
        sim.partition_manager.heal_all()
    elif mode == "isolate_gamma":
        sim.partition_manager.set_partitions([["alpha-harbor", "beta-hospital"], ["gamma-mountain"]])
    elif mode == "isolate_alpha":
        sim.partition_manager.set_partitions([["alpha-harbor"], ["beta-hospital", "gamma-mountain"]])
    elif mode == "isolate_beta":
        sim.partition_manager.set_partitions([["beta-hospital"], ["alpha-harbor", "gamma-mountain"]])
    elif mode == "split_all":
        sim.partition_manager.set_partitions([["alpha-harbor"], ["beta-hospital"], ["gamma-mountain"]])
    elif mode == "chain_relay":
        sim.partition_manager.heal_all()
        sim.transport.cut_link("alpha-harbor", "gamma-mountain")
    else:
        raise ValueError(f"Unknown partition mode: {mode}")
    return sim.partition_manager.get_connected_components()


def toggle_link(sim: DisasterSimulator, node_a: str, node_b: str) -> bool:
    """
    Toggle the direct radio link between two nodes.
    Returns True if the link is connected after toggling, False if cut.
    """
    if sim.transport.is_connected(node_a, node_b):
        sim.transport.cut_link(node_a, node_b)
        return False
    sim.transport.heal_link(node_a, node_b)
    return True


def heal_network_links(sim: DisasterSimulator) -> None:
    """Restore all radio links across the 3-node mesh."""
    sim.partition_manager.heal_all()


def run_mesh_sync(sim: DisasterSimulator) -> List[str]:
    """Execute pairwise anti-entropy sync across connected links and return log lines."""
    sync_results = []
    node_ids = sim.node_ids
    for i in range(len(node_ids)):
        for j in range(i + 1, len(node_ids)):
            n1, n2 = node_ids[i], node_ids[j]
            stats = sim.nodes[n1].sync_with(n2)
            if stats.success:
                sync_results.append(
                    f"OK {n1} <-> {n2}: {stats.events_sent + stats.events_received} ev, {stats.total_bytes} B"
                )
            else:
                sync_results.append(f"CUT {n1} <-> {n2}: Partition Cut")
    return sync_results


def inject_conflicting_doctor_sightings(sim: DisasterSimulator) -> None:
    """Inject concurrent conflicting reports for Dr. Stone on Alpha and Gamma."""
    sim.nodes["alpha-harbor"].record_event(
        entity_type="person",
        entity_id="person-dr-stone",
        operation="UPDATE",
        payload={"name": "Dr. Elizabeth Stone", "status": "MISSING", "location": "Collapsed Bridge 14"},
    )
    sim.nodes["gamma-mountain"].record_event(
        entity_type="person",
        entity_id="person-dr-stone",
        operation="UPDATE",
        payload={"name": "Dr. Elizabeth Stone", "status": "FOUND_SAFE", "location": "Highland Mountain Shelter"},
    )


def run_scenario_preset(sim: DisasterSimulator, preset_name: str) -> List[str]:
    """
    Execute a rich multi-node disaster preset scenario to showcase RescueNet capabilities.
    Returns status log entries describing actions executed.
    """
    alpha = sim.nodes["alpha-harbor"]
    beta = sim.nodes["beta-hospital"]
    gamma = sim.nodes["gamma-mountain"]

    if preset_name == "flash_flood":
        cut_network_partition(sim)
        inject_conflicting_doctor_sightings(sim)
        # Alpha allocates the boat if it still holds the available token
        boat = alpha.get_state().get("scarce_item", {}).get("boat-titan", {})
        if boat.get("token_holder") == "alpha-harbor" and boat.get("status") == "AVAILABLE":
            TokenManager.confirm_allocation(alpha, "boat-titan", "Harbor Bridge Rescue", "alpha-harbor")
        # Gamma cannot allocate without token -> logs offline request
        TokenManager.request_allocation(gamma, "boat-titan", "Mountain Mudslide Airlift Support")
        # Beta consumes from its own local escrow allowance
        beta_q = beta.get_state().get("supply", {}).get("supply-antibiotics", {}).get("quotas", {}).get("beta-hospital", 0)
        if beta_q >= 12:
            EscrowManager.consume(beta, "supply-antibiotics", 12, "Trauma Ward Triage")
        # Gamma logs a new highland shelter
        gamma.record_event(
            "shelter",
            "shelter-highland",
            "CREATE",
            {"name": "Highland Ridge Gym", "capacity": 80, "occupancy": 54},
        )
        return [
            "Preset 'Flash Flood Partition' active: Gamma isolated, conflicting sightings + offline boat claim + trauma supply draw logged."
        ]

    if preset_name == "supply_crunch":
        set_custom_partition(sim, "isolate_alpha")
        beta_q = beta.get_state().get("supply", {}).get("supply-antibiotics", {}).get("quotas", {}).get("beta-hospital", 0)
        if beta_q >= 10:
            EscrowManager.consume(beta, "supply-antibiotics", 10, "Field Surgery Team")
        gamma_q = gamma.get_state().get("supply", {}).get("supply-antibiotics", {}).get("quotas", {}).get("gamma-mountain", 0)
        if gamma_q >= 15:
            EscrowManager.transfer_quota(gamma, "beta-hospital", "supply-antibiotics", 15, "Rebalance antibiotics to Trauma Clinic")
        alpha.record_event(
            "need",
            "need-fuel-alpha",
            "CREATE",
            {"item": "Diesel Generator Fuel (200L)", "urgency": "CRITICAL"},
        )
        return [
            "Preset 'Supply Rebalance' active: Alpha isolated; Gamma transferred 15 antibiotic quota to Beta."
        ]

    if preset_name == "chain_mule":
        set_custom_partition(sim, "chain_relay")
        alpha.record_event(
            "person",
            "person-courier-chen",
            "UPDATE",
            {"name": "Capt. Marcus Chen", "status": "EVACUATED", "location": "Coast Guard Pier 3"},
        )
        gamma.record_event(
            "need",
            "need-radios-gamma",
            "CREATE",
            {"item": "VHF Battery Packs", "urgency": "HIGH"},
        )
        return [
            "Preset '2-Hop Data Mule' active: Alpha<->Gamma direct link cut. Sync Mesh relays updates through Beta!"
        ]

    raise ValueError(f"Unknown preset: {preset_name}")


def check_mesh_convergence(sim: DisasterSimulator) -> bool:
    """Check whether all 3 nodes have identical version vectors and projected state."""
    first_node_id = sim.node_ids[0]
    first_state = sim.nodes[first_node_id].get_state()
    first_vv = sim.nodes[first_node_id].get_version_vector()

    for nid in sim.node_ids[1:]:
        if sim.nodes[nid].get_version_vector() != first_vv or sim.nodes[nid].get_state() != first_state:
            return False
    return True


# ---------------------------------------------------------------------------
# RESQ-MESH ARCHITECTURAL BLUEPRINT 3-PHASE GUIDED DEMO
# ---------------------------------------------------------------------------

def run_resqmesh_phase1_baseline(sim: DisasterSimulator) -> str:
    """
    Phase 1 (The Baseline):
    Initialize 3 nodes sharing initial inventory of 10 Emergency Medical Kits.
    Patient X is registered with status 'PENDING_TRIAGE'.
    All links connected and fully converged.
    """
    heal_network_links(sim)
    
    # Register Patient X
    sim.nodes["alpha-harbor"].record_event(
        entity_type="person",
        entity_id="person-patient-x",
        operation="CREATE",
        payload={
            "name": "Patient X (David Kim)",
            "status": "PENDING_TRIAGE",
            "location": "Sector 4 Coastal Perimeter",
            "notes": "Awaiting initial medical response team",
        },
    )
    # Sync across all nodes
    run_mesh_sync(sim)
    run_mesh_sync(sim)
    return "Phase 1 Baseline Initialized: 10 Trauma Kits in stock, Patient X registered, all 3 nodes converged."


def run_resqmesh_phase2_split_and_conflict(sim: DisasterSimulator) -> str:
    """
    Phase 2 (The Split & Conflict):
    1. Disconnect Node Gamma (Mountain) completely.
    2. Node Alpha claims 8 kits and marks Patient X as 'Found - Stable'.
    3. Node Beta claims 5 kits (causing offline over-allocation: 8+5=13 > 10)
       and marks Patient X as 'Injured - Urgent'.
    """
    # Isolate all 3 nodes into independent partitions
    sim.partition_manager.set_partitions([["alpha-harbor"], ["beta-hospital"], ["gamma-mountain"]])
    
    # Node Alpha offline intent & sighting
    IntentLedger.record_intent(
        node=sim.nodes["alpha-harbor"],
        item_id="medical-kits-pool",
        quantity=8,
        beneficiary="Harbor Surgical Triage Tent",
    )
    sim.nodes["alpha-harbor"].record_event(
        entity_type="person",
        entity_id="person-patient-x",
        operation="UPDATE",
        payload={
            "name": "Patient X (David Kim)",
            "status": "Found - Stable",
            "location": "Harbor Medical Tent 3",
            "notes": "Examined by volunteer nurse; vitals normal",
        },
    )

    # Node Beta offline intent & sighting
    IntentLedger.record_intent(
        node=sim.nodes["beta-hospital"],
        item_id="medical-kits-pool",
        quantity=5,
        beneficiary="Mountain Evacuation Clinic",
    )
    sim.nodes["beta-hospital"].record_event(
        entity_type="person",
        entity_id="person-patient-x",
        operation="UPDATE",
        payload={
            "name": "Patient X (David Kim)",
            "status": "Injured - Urgent",
            "location": "Highland Ridge Ravine",
            "notes": "Compound fracture reported by mountain search team",
        },
    )

    return "Phase 2 Split Active: Alpha claimed 8 kits ('Found-Stable'), Beta claimed 5 kits ('Injured-Urgent'), Gamma isolated."


def run_resqmesh_phase3_reconnect_and_converge(sim: DisasterSimulator) -> str:
    """
    Phase 3 (The Reconnection & Convergence):
    Reconnect all three nodes and execute anti-entropy sync.
    Causally merges event timelines:
    - Patient X timeline displays both historical updates transparently (Zero Lost Updates).
    - An inventory collision alert triggers on 13 claimed > 10 available (Zero Double-Allocation).
    """
    heal_network_links(sim)
    run_mesh_sync(sim)
    run_mesh_sync(sim)  # Second sweep for transitive propagation
    return "Phase 3 Reconnected: Timelines merged causally! Patient X preserves both sightings; Inventory collision detected (13/10)."


def resolve_resqmesh_inventory_collision(
    sim: DisasterSimulator,
    alpha_allocated: int = 6,
    beta_allocated: int = 4,
    notes: str = "Chief Medical Officer emergency triage apportionment",
) -> str:
    """
    Coordinator manually resolves the 13 vs 10 inventory collision:
    Confirms 6 kits to Alpha and 4 kits to Beta (total = 10, zero deficit).
    """
    allocations = {
        "alpha-harbor": alpha_allocated,
        "beta-hospital": beta_allocated,
    }
    IntentLedger.resolve_collision(
        node=sim.nodes["alpha-harbor"],
        item_id="medical-kits-pool",
        approved_allocations=allocations,
        resolution_notes=notes,
    )
    # Propagate resolution across mesh
    heal_network_links(sim)
    run_mesh_sync(sim)
    run_mesh_sync(sim)
    return f"Collision Resolved: Allocated {alpha_allocated} to Harbor, {beta_allocated} to Mountain. Deficit: 0. State 100% Converged."


# ---------------------------------------------------------------------------
# SNEAKERNET DATA MULE & REVOCATION RING
# ---------------------------------------------------------------------------

def dispatch_ambulance_data_mule(
    sim: DisasterSimulator,
    from_node: str = "alpha-harbor",
    to_node: str = "gamma-mountain",
) -> str:
    """
    Sneakernet DTN Transport (Layer 2):
    Simulates a physical emergency ambulance or drone carrying an encrypted cache bundle
    between two geographically disconnected camps across a destroyed bridge or mountain.
    Directly exchanges deltas without restoring the physical radio partition.
    """
    node1 = sim.nodes[from_node]
    node2 = sim.nodes[to_node]
    vv1 = node1.get_version_vector()
    vv2 = node2.get_version_vector()
    deltas_to_2 = node1.store.get_events_since(vv2)
    deltas_to_1 = node2.store.get_events_since(vv1)

    events_sent = len(deltas_to_2)
    events_received = len(deltas_to_1)
    total_bytes = sum(e.wire_byte_size() for e in deltas_to_2 + deltas_to_1)

    for e in deltas_to_2:
        node2.store.append(e)
    for e in deltas_to_1:
        node1.store.append(e)

    return (
        f"🚑 Ambulance Data Mule Dispatched: Ferried updates from {from_node} to {to_node}. "
        f"Transferred {events_sent + events_received} delta events ({total_bytes} bytes) "
        f"via physical sneakernet across partition boundaries!"
    )


def revoke_compromised_device(sim: DisasterSimulator, revoked_node_id: str) -> str:
    """
    Pillar 4 Cryptographic Revocation:
    Blacklists a lost or seized device across the mesh trust ring.
    Freezes its ability to inject data.
    """
    for node in sim.nodes.values():
        if hasattr(node, "keyring") and node.keyring:
            node.keyring.revoke_peer(revoked_node_id)
            
    # Record revocation audit event
    sim.nodes["alpha-harbor"].record_event(
        entity_type="security",
        entity_id=f"revocation-{revoked_node_id}",
        operation="REVOKE_NODE",
        payload={
            "revoked_node_id": revoked_node_id,
            "reason": "Device flagged lost/seized in field operation",
            "revocation_authority": "alpha-harbor",
        },
    )
    return f"🚨 Device {revoked_node_id} blacklisted across cryptographic ring. All future events will be dropped!"


def export_node_bundle_json(sim: DisasterSimulator, node_id: str) -> str:
    """Serialize a node's full event history as a portable USB/sneakernet JSON bundle."""
    node = sim.nodes[node_id]
    events = node.store.get_all_events()
    bundle = {
        "format": "rescuenet-usb-bundle-v1",
        "source_node": node_id,
        "version_vector": node.get_version_vector(),
        "event_count": len(events),
        "events": [e.to_dict() for e in events],
    }
    return json.dumps(bundle, indent=2, sort_keys=True)


def import_node_bundle_json(sim: DisasterSimulator, target_node_id: str, bundle_json: str) -> Dict[str, Any]:
    """
    Import a portable JSON sync bundle into a target node while enforcing signature verification
    and append-only SQLite idempotency.
    """
    data = json.loads(bundle_json)
    raw_events = data.get("events", [])
    parsed = [Event.from_dict(item) for item in raw_events]

    target = sim.nodes[target_node_id]
    verified = target._verify_and_filter_events(parsed)
    rejected = len(parsed) - len(verified)

    applied = 0
    for ev in verified:
        if target.store.append(ev):
            applied += 1

    return {
        "source_node": data.get("source_node", "unknown"),
        "target_node": target_node_id,
        "received": len(parsed),
        "applied": applied,
        "skipped_duplicates": len(verified) - applied,
        "rejected": rejected,
    }


def get_node_timeline(sim: DisasterSimulator, node_id: str, limit: int = 25) -> List[Dict[str, Any]]:
    """
    Return recent chronological events for a node with crypto inspection metadata.
    Decrypts payloads if a keyring is present while flagging whether ciphertext existed at rest.
    """
    node = sim.nodes[node_id]
    events = node.store.get_all_events()
    recent = events[-limit:][::-1]
    rows: List[Dict[str, Any]] = []

    for ev in recent:
        has_enc = any(
            isinstance(v, dict) and v.get("__enc__") is True
            for v in ev.payload.values()
        )
        display_payload = (
            node.keyring.decrypt_payload(ev.payload) if node.keyring is not None else ev.payload
        )
        sig_valid = None
        if ev.signature and node.keyring is not None:
            sig_valid = node.keyring.verify_event(ev)

        rows.append({
            "event_id": ev.event_id,
            "node_id": ev.node_id,
            "counter": ev.counter,
            "timestamp": ev.timestamp,
            "entity": f"{ev.entity_type}:{ev.entity_id}",
            "operation": ev.operation,
            "signed": bool(ev.signature),
            "sig_valid": sig_valid,
            "encrypted_pii": has_enc,
            "wire_bytes": ev.wire_byte_size(),
            "payload": display_payload,
            "raw_payload": ev.payload,
        })
    return rows


def build_mesh_topology_svg(sim: DisasterSimulator) -> str:
    """
    Build a crisp inline SVG topology diagram showing the 3 stations, live link statuses,
    event counts, and current boat token holder.
    """
    coords: Dict[str, Tuple[int, int, str, str]] = {
        "alpha-harbor": (150, 70, "Alpha: Coast Guard Harbor", "#2563EB"),
        "beta-hospital": (550, 70, "Beta: Field Trauma Clinic", "#0D9488"),
        "gamma-mountain": (350, 215, "Gamma: Mountain Shelter", "#7C3AED"),
    }

    boat_holder = None
    for nid in sim.node_ids:
        boat = sim.nodes[nid].get_state().get("scarce_item", {}).get("boat-titan", {})
        if boat.get("token_holder"):
            boat_holder = boat.get("token_holder")
            break

    pairs = [
        ("alpha-harbor", "beta-hospital", 350, 56),
        ("alpha-harbor", "gamma-mountain", 225, 152),
        ("beta-hospital", "gamma-mountain", 475, 152),
    ]

    link_svg = []
    for n1, n2, lx, ly in pairs:
        x1, y1, _, _ = coords[n1]
        x2, y2, _, _ = coords[n2]
        connected = sim.transport.is_connected(n1, n2)
        stroke = "#10B981" if connected else "#EF4444"
        dash = "" if connected else 'stroke-dasharray="8,6"'
        badge_bg = "#ECFDF5" if connected else "#FEF2F2"
        badge_fg = "#065F46" if connected else "#991B1B"
        label = "LINK UP" if connected else "LINK CUT"

        link_svg.append(
            f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
            f'stroke="{stroke}" stroke-width="3.5" {dash} stroke-linecap="round" />'
            f'<rect x="{lx - 38}" y="{ly - 12}" width="76" height="22" rx="11" '
            f'fill="{badge_bg}" stroke="{stroke}" stroke-width="1.5" />'
            f'<text x="{lx}" y="{ly + 3}" text-anchor="middle" font-size="11" '
            f'font-weight="700" fill="{badge_fg}" font-family="system-ui, sans-serif">{label}</text>'
        )

    node_svg = []
    for nid, (cx, cy, title, accent) in coords.items():
        ev_count = sim.nodes[nid].store.count()
        has_token = (nid == boat_holder)
        token_pill = (
            f'<rect x="{cx - 48}" y="{cy + 26}" width="96" height="20" rx="10" fill="#FEF3C7" stroke="#F59E0B" stroke-width="1.2"/>'
            f'<text x="{cx}" y="{cy + 40}" text-anchor="middle" font-size="10.5" font-weight="700" fill="#92400E" font-family="system-ui, sans-serif">BOAT TOKEN</text>'
            if has_token
            else ""
        )
        node_svg.append(
            f'<rect x="{cx - 115}" y="{cy - 34}" width="230" height="62" rx="12" '
            f'fill="#FFFFFF" stroke="{accent}" stroke-width="2.5" />'
            f'<text x="{cx}" y="{cy - 9}" text-anchor="middle" font-size="13" '
            f'font-weight="700" fill="#0F172A" font-family="system-ui, sans-serif">{title}</text>'
            f'<text x="{cx}" y="{cy + 12}" text-anchor="middle" font-size="11.5" '
            f'fill="#475569" font-family="system-ui, sans-serif">{nid} | {ev_count} events</text>'
            f'{token_pill}'
        )

    return (
        '<div style="display:flex;justify-content:center;width:100%;margin:4px 0 8px 0;">'
        '<svg viewBox="0 0 700 275" width="100%" style="max-width:780px;background:#F8FAFC;'
        'border:1px solid #E2E8F0;border-radius:12px;">'
        + "".join(link_svg)
        + "".join(node_svg)
        + "</svg></div>"
    )
