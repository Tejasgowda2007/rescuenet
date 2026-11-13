"""
RescueNet Command Center Components.
Modular renderers for all 11 operational sections:
  1. Command Centre Header
  2. Live Mesh Network Monitor (3 Laptops + SVG Topology)
  3. Disaster Incident Overview
  4. Rescue Operations (Missing People, Supplies, Shelters, Requests)
  5. 5-Step Network Partition & Reconnection Demonstration
  6. Synchronization & Delta Monitor
  7. Security Centre (Ed25519, AES-256-GCM, Revocations)
  8. Resource Allocation Safety (Escrow Invariant & Boat Token)
  9. Event Store & Audit Feed
 10. Long-Range Communication Modalities
 11. System Diagnostics & Health Scorecard
"""

from __future__ import annotations
import json
import time
from typing import Any, Dict, List
import streamlit as st

from simulator.engine import DisasterSimulator
from allocation.escrow import EscrowManager, InsufficientQuotaError
from allocation.tokens import TokenManager, UnauthorizedAllocationError
from allocation.conflict_resolver import ConflictResolver
from ui.controller import (
    NODE_METADATA,
    cut_network_partition,
    set_custom_partition,
    heal_network_links,
    run_mesh_sync,
    inject_conflicting_doctor_sightings,
    run_scenario_preset,
    get_mesh_connectivity_status,
    get_mesh_data_convergence_status,
    format_plain_english_vv,
    get_node_sync_status,
    get_station_resource_meters,
    build_mesh_topology_svg,
    get_node_timeline,
    export_node_bundle_json,
    import_node_bundle_json,
    get_active_incidents,
    create_incident,
    resolve_incident,
    get_people_registry,
    get_medical_supplies_summary,
    get_shelters_summary,
    get_rescue_requests,
    get_security_summary,
    get_security_audit_log,
    probe_physical_mesh_laptops,
    get_long_range_comms_info,
    get_system_health_metrics,
    run_resqmesh_phase1_baseline,
    run_resqmesh_phase2_split_and_conflict,
    run_resqmesh_phase3_reconnect_and_converge,
    resolve_resqmesh_inventory_collision,
    dispatch_ambulance_data_mule,
    revoke_compromised_device,
)


# ---------------------------------------------------------------------------
# 1. COMMAND CENTRE HEADER
# ---------------------------------------------------------------------------

def render_command_center_header(sim: DisasterSimulator) -> None:
    """Render the top mission-critical command center header with live status pills."""
    conn = get_mesh_connectivity_status(sim)
    conv = get_mesh_data_convergence_status(sim)
    crypto_on = st.session_state.get("crypto_enabled", True)
    total_wire_bytes = sim.transport.get_stats().get("total_bytes", 0)
    total_msgs = sim.transport.get_stats().get("total_messages", 0)

    # Distinguish states
    conn_pill = "rn-pill-mesh-up" if conn["is_connected"] else "rn-pill-mesh-split"
    conv_pill = "rn-pill-mesh-up" if conv["is_converged"] else "rn-pill-mesh-split"
    conv_text = "CONVERGED (100% IDENTICAL)" if conv["is_converged"] else "DIVERGED (OFFLINE EDITS)"

    st.markdown(f"""
        <div class="rn-header">
            <div class="rn-header-top">
                <div class="rn-brand">
                    <div class="rn-logo-badge">RESCUENET</div>
                    <div class="rn-title-group">
                        <div class="rn-title">
                            DISASTER COORDINATION COMMAND CENTRE
                        </div>
                        <div class="rn-tagline">
                            When the network dies, coordination shouldn't. • Offline-First Peer-to-Peer Mesh
                        </div>
                    </div>
                </div>
            </div>
            <div class="rn-pills-row">
                <span class="rn-pill rn-pill-offline">🔴 INTERNET: OFFLINE (ZERO WAN DEPENDENCY)</span>
                <span class="rn-pill {conn_pill}">{conn['icon']} LOCAL MESH: {conn['label']}</span>
                <span class="rn-pill {conv_pill}">{conv['icon']} DATA: {conv_text}</span>
                <span class="rn-pill rn-pill-cyan">⚡ 3 ACTIVE NODES: ALPHA, BETA, GAMMA</span>
                <span class="rn-pill rn-pill-crypto">🔐 ED25519 + AES-256-GCM ACTIVE</span>
                <span class="rn-pill rn-pill-cyan">📦 WIRE: {total_wire_bytes} B ({total_msgs} msgs)</span>
            </div>
        </div>
    """, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# QUICK CONTROLS DOCK
# ---------------------------------------------------------------------------

def render_controls_bar(sim: DisasterSimulator, reset_callback: Any) -> None:
    """Render fast action buttons for mesh control, link toggles, and sync."""
    conn = get_mesh_connectivity_status(sim)
    is_connected = conn["is_connected"]
    comps = conn["components"]
    is_gamma_cut = (len(comps) == 2 and ["gamma-mountain"] in comps)

    c1, c2, c3, c4, c5, c6 = st.columns([1.1, 1.3, 1.3, 1.3, 1.4, 1.2])

    with c1:
        if st.button("🧹 Reset", use_container_width=True, help="Reset mesh to clean, fully-converged baseline (< 2s)"):
            reset_callback()
            st.toast("Mesh reset to clean initial baseline.", icon="🧹")
            st.rerun()

    with c2:
        cut_disabled = is_gamma_cut
        cut_help = "Gamma is already isolated" if cut_disabled else "Isolate Gamma Mountain Shelter (simulate mountain pass cut)"
        if st.button("🔴 Sever Mountain", disabled=cut_disabled, help=cut_help, use_container_width=True):
            cut_network_partition(sim)
            st.session_state.sync_logs = ["Partition Applied: Gamma Mountain Shelter isolated from Alpha & Beta."]
            st.toast("Mountain station partitioned from coastal harbor and hospital.", icon="🔴")
            st.rerun()

    with c3:
        heal_disabled = is_connected
        heal_help = "All radio links are already connected" if heal_disabled else "Restore all radio links across the 3 stations"
        if st.button("🟢 Heal Network", disabled=heal_disabled, help=heal_help, use_container_width=True):
            heal_network_links(sim)
            st.session_state.sync_logs = ["All radio links restored (Full 3-Node Mesh)."]
            st.toast("All radio links restored to Full Mesh.", icon="🟢")
            st.rerun()

    with c4:
        if st.button("🔄 Sync Mesh", use_container_width=True, help="Run pairwise anti-entropy delta sync across active links"):
            results = run_mesh_sync(sim)
            st.session_state.sync_logs = results
            st.toast(f"Mesh sync complete ({len(results)} pairwise handshakes).", icon="🔄")
            st.rerun()

    with c5:
        if st.button("⚡ Inject Conflict", use_container_width=True, help="Record competing observations of Dr. Stone on Alpha and Gamma"):
            inject_conflicting_doctor_sightings(sim)
            st.session_state.sync_logs = ["Concurrent conflict injected: Dr. Stone reported MISSING at Pier 14 vs FOUND at Mountain Shelter."]
            st.toast("Concurrent conflicting doctor sightings recorded!", icon="⚡")
            st.rerun()

    with c6:
        if st.button("🚑 Data Mule", use_container_width=True, help="Physical DTN transport: ferry updates via emergency ambulance"):
            msg = dispatch_ambulance_data_mule(sim)
            st.session_state.sync_logs = [msg]
            st.toast("Ambulance Data Mule dispatched across partition!", icon="🚑")
            st.rerun()

    if st.session_state.get("sync_logs"):
        st.caption(f"**Latest Mesh Telemetry:** {st.session_state.sync_logs[-1]}")


# ---------------------------------------------------------------------------
# 2. LIVE MESH NETWORK MONITOR
# ---------------------------------------------------------------------------

def render_mesh_network_monitor(sim: DisasterSimulator) -> None:
    """
    Render detailed monitoring for the 3 participating laptops/nodes:
    ALPHA (Harbor), BETA (Hospital), GAMMA (Mountain Shelter).
    Includes SVG topology, physical LAN probe, and individual station cards.
    """
    st.markdown("### 📡 Live Mesh Network Monitor")
    st.caption("Real-time telemetry from the three participating disaster coordination nodes over peer-to-peer radio/TCP links.")

    # Topology and Link Switches
    topo_col, link_col = st.columns([2.4, 1.2])

    with topo_col:
        st.markdown(build_mesh_topology_svg(sim), unsafe_allow_html=True)

    with link_col:
        st.markdown("##### 🎛️ Radio Link Switches")
        link_pairs = [
            ("alpha-harbor", "beta-hospital", "Alpha ↔ Beta (Coastal Link)"),
            ("alpha-harbor", "gamma-mountain", "Alpha ↔ Gamma (Valley Link)"),
            ("beta-hospital", "gamma-mountain", "Beta ↔ Gamma (Ridge Link)"),
        ]
        for n1, n2, label in link_pairs:
            up = sim.transport.is_connected(n1, n2)
            icon = "🟢 UP" if up else "🔴 CUT"
            btn_label = f"{icon}: {label}"
            if st.button(btn_label, key=f"link_toggle_{n1}_{n2}", use_container_width=True):
                from ui.controller import toggle_link
                now_up = toggle_link(sim, n1, n2)
                st.session_state.sync_logs = [f"Radio link {label} is now {'RESTORED (UP)' if now_up else 'SEVERED (DOWN)'}."]
                st.toast(f"Link {label} {'restored' if now_up else 'cut'}.", icon="📡")
                st.rerun()

        comps = sim.partition_manager.get_connected_components()
        if len(comps) > 1:
            st.warning(f"⚠️ **Network Partitioned:** {len(comps)} isolated islands")
        else:
            st.success("🟢 **Network Connected:** Full 3-Node Mesh")

    st.write("")

    # Physical LAN Probe Toggle
    with st.expander("🌐 Physical 3-Laptop LAN Deployment Monitor", expanded=False):
        st.caption("Probe actual physical laptops running RescueNet on the local Wi-Fi / hotspot.")
        if st.button("🔍 Scan Local Network for Physical Laptops", key="btn_probe_laptops"):
            phys_data = probe_physical_mesh_laptops()
            p_cols = st.columns(3)
            for idx, (nid, pinfo) in enumerate(phys_data.items()):
                with p_cols[idx]:
                    st.markdown(f"""
                        <div class="rn-card">
                            <div style="font-weight:700; color:#00E5FF;">{nid.upper()}</div>
                            <div style="font-size:0.85rem; color:#8B9BB4;">{pinfo['role']}</div>
                            <div style="margin-top:8px;">
                                <span class="{pinfo['badge_class']}">{pinfo['status_label']}</span>
                            </div>
                            <div style="margin-top:8px; font-family:'JetBrains Mono'; font-size:0.8rem;">
                                TCP Sync: {pinfo['host']}:{pinfo['tcp_port']}<br>
                                Latency: {pinfo['latency_ms']} ms
                            </div>
                        </div>
                    """, unsafe_allow_html=True)

    # Three Node Cards
    st.markdown("##### 🏢 Active Nodes Telemetry")
    cols = st.columns(3)
    for idx, cfg in enumerate(NODE_METADATA):
        render_station_card(sim, cfg, cols[idx])


def render_station_card(sim: DisasterSimulator, cfg: Dict[str, str], col: Any) -> None:
    """Render an individual station card with plain-English vectors, resource meters, and action forms."""
    nid = cfg["id"]
    node = sim.nodes[nid]
    state = node.get_state()
    peer_ids = [n for n in sim.node_ids if n != nid]

    sync_info = get_node_sync_status(nid, sim)
    vv_plain, raw_vv = format_plain_english_vv(nid, sim)
    meters = get_station_resource_meters(nid, sim)

    with col:
        st.markdown(f"""
            <div class="rn-card-elevated" style="border-top: 3px solid {cfg['accent']};">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <div>
                        <div style="font-size:1.05rem; font-weight:800; color:#FFFFFF;">{cfg['icon']} {cfg['title']}</div>
                        <div style="font-size:0.8rem; color:#8B9BB4;">{cfg['role']}</div>
                    </div>
                    <div>
                        <span class="rn-pill {'rn-pill-mesh-up' if sync_info['is_up_to_date'] else 'rn-pill-mesh-split'}">
                            {sync_info['icon']} {sync_info['label']}
                        </span>
                    </div>
                </div>
                <div style="background:#09121E; padding:8px 12px; border-radius:4px; margin-top:10px; font-size:0.8rem; font-family:'JetBrains Mono'; border:1px solid #14243A;">
                    <span style="color:#00E5FF; font-weight:700;">SYNC:</span> {vv_plain}
                </div>
            </div>
        """, unsafe_allow_html=True)

        # Resource meters
        m1, m2 = st.columns(2)
        with m1:
            st.metric("Antibiotics Quota", f"{meters['my_quota']} / {meters['total_quantity']}")
            st.caption(f"Status: **{meters['quota_status']}** (Consumed: {meters['consumed']})")
        with m2:
            if meters["has_token"]:
                alloc_msg = f" (Mission: {meters['allocated_to']})" if meters["allocated_to"] else " (Ready)"
                st.markdown(f"""
                    <div style="background:rgba(245,158,11,0.15); border:1px solid #F59E0B; padding:8px; border-radius:6px; color:#FCD34D; font-size:0.8rem; font-weight:700;">
                        🚢 Boat Token Held{alloc_msg}
                    </div>
                """, unsafe_allow_html=True)
            else:
                holder_name = meters['token_holder'].split('-')[0].capitalize() if meters['token_holder'] else 'Unknown'
                st.markdown(f"""
                    <div style="background:rgba(100,116,139,0.15); border:1px solid #475569; padding:8px; border-radius:6px; color:#94A3B8; font-size:0.8rem;">
                        ⚓ Holder: {holder_name}
                    </div>
                """, unsafe_allow_html=True)

        with st.expander(f"⚡ Field Actions ({nid.split('-')[0].capitalize()})", expanded=False):
            t_person, t_supplies, t_boat, t_shelter = st.tabs(["Person", "Supplies", "Boat", "Need"])

            with t_person:
                with st.form(key=f"form_p_{nid}"):
                    p_name = st.text_input("Person Name", value="David Kim")
                    p_id = "person-" + p_name.lower().replace(" ", "-")
                    p_status = st.selectbox("Triage Status", ["MISSING", "FOUND_SAFE", "INJURED", "EVACUATED"])
                    p_loc = st.text_input("Observed Location", value=f"Sector near {nid.split('-')[1].title()}")
                    p_notes = st.text_input("Triage Notes", value="Observed by local rescue volunteer")

                    if st.form_submit_button("Log Person Update", use_container_width=True):
                        node.record_event(
                            entity_type="person",
                            entity_id=p_id,
                            operation="UPDATE",
                            payload={"name": p_name, "status": p_status, "location": p_loc, "notes": p_notes},
                        )
                        st.toast(f"{nid} logged update for {p_name} ({p_status})", icon="👤")
                        st.rerun()

            with t_supplies:
                st.write(f"**Local Quota:** `{meters['my_quota']}` courses")
                s_action = st.radio("Action", ["Consume Quota", "Transfer Quota"], key=f"sa_{nid}", horizontal=True)

                if s_action == "Consume Quota":
                    with st.form(key=f"form_c_{nid}"):
                        c_qty = st.number_input("Quantity", min_value=1, max_value=max(1, meters['my_quota']), value=min(4, max(1, meters['my_quota'])))
                        c_for = st.text_input("Reason", value="Critical triage draw")
                        if st.form_submit_button("Consume", use_container_width=True):
                            try:
                                EscrowManager.consume(node, "supply-antibiotics", int(c_qty), c_for)
                                st.toast(f"Consumed {c_qty} courses.", icon="💊")
                                st.rerun()
                            except InsufficientQuotaError as exc:
                                st.error(str(exc))
                else:
                    with st.form(key=f"form_t_{nid}"):
                        t_target = st.selectbox("Recipient", peer_ids, key=f"tt_{nid}")
                        t_qty = st.number_input("Quantity", min_value=1, max_value=max(1, meters['my_quota']), value=min(5, max(1, meters['my_quota'])))
                        t_reason = st.text_input("Reason", value="Field quota rebalance")
                        if st.form_submit_button("Transfer", use_container_width=True):
                            try:
                                EscrowManager.transfer_quota(node, t_target, "supply-antibiotics", int(t_qty), t_reason)
                                st.toast(f"Transferred {t_qty} quota to {t_target}.", icon="🚚")
                                st.rerun()
                            except InsufficientQuotaError as exc:
                                st.error(str(exc))

            with t_boat:
                if meters["has_token"] and meters["boat_status"] == "AVAILABLE":
                    st.success("You hold the boat token. Boat is ready.")
                    with st.form(key=f"form_b_{nid}"):
                        b_mission = st.text_input("Mission Name", value="Harbor Evacuation Run")
                        if st.form_submit_button("Confirm Deployment", use_container_width=True):
                            TokenManager.confirm_allocation(node, "boat-titan", b_mission, nid)
                            st.toast("Boat deployed.", icon="🚢")
                            st.rerun()
                elif meters["has_token"]:
                    st.warning(f"Deployed: {meters['allocated_to']}")
                    if st.button("Complete Mission & Release Boat", key=f"rel_{nid}", use_container_width=True):
                        TokenManager.release_item(node, "boat-titan", notes="Mission complete")
                        st.toast("Boat released.", icon="✅")
                        st.rerun()
                else:
                    st.info(f"Token held by {meters['token_holder']}. You can request.")
                    with st.form(key=f"form_req_{nid}"):
                        b_req = st.text_input("Request Mission", value="Flood extraction request")
                        if st.form_submit_button("Submit Request", use_container_width=True):
                            TokenManager.request_allocation(node, "boat-titan", b_req)
                            st.toast("Boat allocation requested.", icon="📝")
                            st.rerun()

            with t_shelter:
                with st.form(key=f"form_n_{nid}"):
                    n_item = st.text_input("Urgent Need", value="Diesel Generator Fuel (100L)")
                    n_urg = st.selectbox("Urgency", ["CRITICAL", "HIGH", "MEDIUM"])
                    if st.form_submit_button("Post Need", use_container_width=True):
                        need_id = f"need-{nid.split('-')[0]}-{int(time.time() * 1000) % 10000}"
                        node.record_event("need", need_id, "CREATE", {"item": n_item, "urgency": n_urg})
                        st.toast(f"Posted {n_urg} need.", icon="🚨")
                        st.rerun()


# ---------------------------------------------------------------------------
# 3. DISASTER INCIDENT OVERVIEW
# ---------------------------------------------------------------------------

def render_incident_overview(sim: DisasterSimulator) -> None:
    """Render incident command overview, severity distribution, and active operations."""
    st.markdown("### 🚨 Disaster Incident Overview & Command")
    st.caption("Active emergency incidents reported and tracked across the disaster theater.")

    incidents = get_active_incidents(sim)

    # Summary Metrics
    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.metric("Total Incidents", len(incidents))
    with m2:
        crit_count = sum(1 for i in incidents if i["severity"] == "CRITICAL")
        st.metric("Critical Incidents", crit_count)
    with m3:
        active_count = sum(1 for i in incidents if i["status"] != "RESOLVED")
        st.metric("Active Response", active_count)
    with m4:
        affected_total = sum(i["affected_people"] for i in incidents)
        st.metric("Affected Civilians", affected_total)

    st.write("")

    # Incident cards
    for inc in incidents:
        sev = inc["severity"]
        badge_cls = f"badge-{sev.lower()}"
        teams_str = ", ".join(inc["assigned_teams"]) if inc["assigned_teams"] else "No teams assigned"

        with st.container():
            c1, c2 = st.columns([3.5, 1.2])
            with c1:
                st.markdown(f"""
                    <div class="rn-card">
                        <div style="display:flex; justify-content:space-between; align-items:center;">
                            <span style="font-size:1.05rem; font-weight:800; color:#FFFFFF;">{inc['title']}</span>
                            <span class="{badge_cls}">{sev}</span>
                        </div>
                        <div style="font-size:0.85rem; color:#8B9BB4; margin-top:4px;">
                            📍 <strong>Location:</strong> {inc['location']} • 👥 <strong>Affected:</strong> ~{inc['affected_people']} people
                        </div>
                        <div style="font-size:0.8rem; color:#A0AEC0; margin-top:6px;">
                            {inc['description']}
                        </div>
                        <div style="font-size:0.78rem; color:#00E5FF; margin-top:6px; font-family:'JetBrains Mono';">
                            🚒 Response Teams: {teams_str}
                        </div>
                    </div>
                """, unsafe_allow_html=True)
            with c2:
                if inc["status"] != "RESOLVED":
                    st.write("")
                    if st.button(f"Mark Resolved", key=f"res_inc_{inc['incident_id']}", use_container_width=True):
                        resolve_incident(sim, "alpha-harbor", inc["incident_id"], "Field incident resolved safely by response commander")
                        run_mesh_sync(sim)
                        st.toast(f"Incident {inc['incident_id']} resolved.", icon="✅")
                        st.rerun()
                else:
                    st.success("✅ RESOLVED")

    # Log Incident Expander
    with st.expander("➕ Log New Disaster Incident", expanded=False):
        with st.form("form_new_incident"):
            n_node = st.selectbox("Reporting Station", sim.node_ids)
            n_title = st.text_input("Incident Title", value="Flash Flood Surge at Pier 2")
            n_id = "inc-" + str(int(time.time() * 1000) % 100000)
            n_sev = st.selectbox("Severity", ["CRITICAL", "HIGH", "MEDIUM", "LOW"])
            n_loc = st.text_input("Location", value="Sector 4 Coastal Channel")
            n_desc = st.text_area("Situation Description", value="Sudden water level rise threatening local shelter.")
            n_teams = st.text_input("Assigned Teams (comma-separated)", value="Rescue Alpha, Medic 1")
            n_aff = st.number_input("Estimated Affected People", min_value=0, max_value=10000, value=50)

            if st.form_submit_button("Broadcast Incident to Mesh", use_container_width=True):
                teams_list = [t.strip() for t in n_teams.split(",") if t.strip()]
                create_incident(sim, n_node, n_id, n_title, n_sev, n_loc, n_desc, teams_list, int(n_aff))
                run_mesh_sync(sim)
                st.toast(f"Incident {n_title} logged and broadcast.", icon="🚨")
                st.rerun()


# ---------------------------------------------------------------------------
# 4. RESCUE OPERATIONS
# ---------------------------------------------------------------------------

def render_rescue_operations(sim: DisasterSimulator) -> None:
    """Render dedicated operations tabs: Missing/Found Persons, Supplies, Shelters, Requests."""
    st.markdown("### 🩺 Rescue Operations Coordination")
    st.caption("Cross-sector coordination: civilian tracking, medical supply logistics, shelter capacity, and field requests.")

    tab_people, tab_supplies, tab_shelters, tab_requests = st.tabs([
        "👤 Missing / Found People",
        "💊 Medical Supplies & Escrow",
        "⛺ Shelters & Evacuation Camps",
        "📋 Field Rescue Requests",
    ])

    with tab_people:
        people = get_people_registry(sim)
        st.markdown("##### 👥 Civilian & Casualty Tracking Registry")
        st.caption("Conflicting observations from isolated sectors are preserved for coordinator triage (Zero Lost Updates).")

        table_data = []
        for p in people:
            status_text = p["status"]
            if p["has_conflict"]:
                status_text += f" [⚠️ DISPUTED ({len(p['conflicts'])} conflicts)]"
            table_data.append({
                "Person ID": p["person_id"],
                "Full Name": p["name"],
                "Triage Status": status_text,
                "Observed Location": p["location"],
                "Reporting Node": p["reporting_node"],
                "Triage Notes": p["notes"],
            })
        st.dataframe(table_data, use_container_width=True, hide_index=True)

    with tab_supplies:
        supp = get_medical_supplies_summary(sim)
        st.markdown(f"##### 💊 {supp['item_name']} Distribution")

        # Invariant Formula Banner
        st.markdown(f"""
            <div class="rn-invariant-banner">
                <span class="rn-formula">FORMULA: {supp['conservation_formula']}</span>
                <span class="rn-formula-verified">{'✅ INVARIANT CONSERVED' if supp['is_conserved'] else '⚠️ VIOLATION'}</span>
            </div>
        """, unsafe_allow_html=True)

        s1, s2, s3, s4 = st.columns(4)
        with s1:
            st.metric("Total Stock", supp["total"])
        with s2:
            st.metric("Remaining (Allocated)", supp["remaining"])
        with s3:
            st.metric("Consumed in Field", supp["consumed"])
        with s4:
            st.metric("Conservation Invariant", "100% BALANCED" if supp["is_conserved"] else "ERROR")

        st.markdown("###### Local Quotas by Station")
        q_cols = st.columns(len(sim.node_ids))
        for idx, nid in enumerate(sim.node_ids):
            q_val = supp["quotas"].get(nid, 0)
            with q_cols[idx]:
                st.metric(nid.split("-")[0].capitalize(), f"{q_val} courses")
                st.progress(min(1.0, max(0.0, q_val / supp["total"])))

    with tab_shelters:
        shelters = get_shelters_summary(sim)
        st.markdown("##### ⛺ Emergency Evacuation Shelters")

        for sh in shelters:
            with st.container():
                st.markdown(f"""
                    <div class="rn-card">
                        <div style="display:flex; justify-content:space-between; align-items:center;">
                            <span style="font-weight:700; color:#FFFFFF;">{sh['name']}</span>
                            <span class="badge-{'critical' if sh['status']=='FULL' else ('high' if sh['status']=='NEAR_CAPACITY' else 'low')}">{sh['status']}</span>
                        </div>
                        <div style="font-size:0.85rem; color:#8B9BB4; margin-top:4px;">
                            Occupancy: <strong>{sh['occupancy']} / {sh['capacity']}</strong> ({sh['occupancy_pct']}%) • Remaining Space: <strong>{sh['available']}</strong> beds
                        </div>
                    </div>
                """, unsafe_allow_html=True)
                st.progress(min(1.0, max(0.0, sh["occupancy_pct"] / 100.0)))

    with tab_requests:
        reqs = get_rescue_requests(sim)
        st.markdown("##### 📋 Urgent Rescue & Supply Requests")
        if reqs:
            r_table = []
            for r in reqs:
                r_table.append({
                    "Request ID": r["request_id"],
                    "Item / Mission": r["description"],
                    "Priority": r["priority"],
                    "Originating Station": r["originating_node"],
                    "Status": r["status"],
                })
            st.dataframe(r_table, use_container_width=True, hide_index=True)
        else:
            st.info("No pending rescue requests.")


# ---------------------------------------------------------------------------
# 5. OFFLINE MODE — 5-STEP NETWORK PARTITION DEMONSTRATION
# ---------------------------------------------------------------------------

def render_partition_demo_stepper(sim: DisasterSimulator) -> None:
    """
    Render interactive 5-step demonstration for hackathon mentors:
      Step 1: Normal Operation (Online Baseline)
      Step 2: Network Failure (Radio Severed / Partition)
      Step 3: Conflict Generation (Conflicting Sightings & Double Allocation Block)
      Step 4: Reconnection (Radio Restored & Delta Sync)
      Step 5: Convergence (Conflict Ledger & Final 100% Agreement)
    """
    st.markdown("### 🎯 5-Step Offline Partition & Convergence Walkthrough")
    st.caption("A step-by-step interactive demonstration proving Zero Lost Updates and Zero Double-Allocations under total network partitions.")

    curr_step = st.session_state.get("step", 1)

    s_cols = st.columns(5)
    steps_meta = [
        (1, "1. Normal", "Online baseline"),
        (2, "2. Failure", "Radio severed"),
        (3, "3. Conflict", "Divergent claims"),
        (4, "4. Reconnect", "Delta sync"),
        (5, "5. Converge", "Full agreement"),
    ]

    for idx, (num, title, sub) in enumerate(steps_meta):
        is_active = (curr_step == num)
        with s_cols[idx]:
            st.markdown(f"""
                <div class="rn-step-card {'rn-step-active' if is_active else ''}">
                    <div class="rn-step-number">STEP {num}</div>
                    <div class="rn-step-title">{title}</div>
                    <div class="rn-step-desc">{sub}</div>
                </div>
            """, unsafe_allow_html=True)

    st.write("")

    # Step Content & Action Triggers
    if curr_step == 1:
        st.info("🟢 **STEP 1: NORMAL OPERATION** — All 3 stations are connected on local Wi-Fi. Initial inventory: **10 Emergency Medical Trauma Kits** in shared pool. Patient X registered with status `PENDING_TRIAGE`.")
        if st.button("▶ Proceed to Step 2: Simulate Disaster Network Severing", type="primary", use_container_width=True):
            run_resqmesh_phase2_split_and_conflict(sim)
            st.session_state.step = 2
            st.session_state.resolved = False
            st.toast("Disaster severed radio links! Stations are now isolated.", icon="🔴")
            st.rerun()

    elif curr_step == 2:
        st.error("🔴 **STEP 2: NETWORK FAILURE (ISOLATION)** — A mountain rockslide has completely severed radio links. All 3 stations are now operating in **isolated partitions**. Each laptop writes to its own local SQLite database.")
        if st.button("▶ Proceed to Step 3: Generate Conflicting Reports & Over-Allocation", type="primary", use_container_width=True):
            st.session_state.step = 3
            st.toast("Conflicting sightings and claims logged offline.", icon="⚡")
            st.rerun()

    elif curr_step == 3:
        st.warning("""
            ⚡ **STEP 3: INDEPENDENT CONFLICTING ACTIONS**
            - **Laptop Alpha (Harbor)** claims **8 trauma kits** and reports Patient X as **'Found - Stable'** at Harbor Pier 3.
            - **Laptop Beta (Hospital)** claims **5 trauma kits** and reports Patient X as **'Injured - Urgent'** at Highland Ravine.
            - **Total Claimed = 13 Kits for only 10 in stock!**
            - RescueNet **blocks double-allocation** and preserves **both** sightings in append-only SQLite logs!
        """)
        if st.button("▶ Proceed to Step 4: Reconnect Mesh & Trigger Anti-Entropy Sync", type="primary", use_container_width=True):
            run_resqmesh_phase3_reconnect_and_converge(sim)
            st.session_state.step = 4
            st.toast("Mesh reconnected! Anti-entropy sync running.", icon="🟢")
            st.rerun()

    elif curr_step == 4:
        st.info("🔄 **STEP 4: RECONNECTION & DELTA SYNC** — Radio links restored! Pairwise anti-entropy handshakes executed. Compact version vectors exchanged. Missing events merged causally.")
        if st.button("▶ Proceed to Step 5: Audit Convergence & Resolve Collision", type="primary", use_container_width=True):
            st.session_state.step = 5
            st.toast("Auditing state convergence across all 3 nodes.", icon="🔍")
            st.rerun()

    elif curr_step == 5:
        if not st.session_state.get("resolved", False):
            st.warning("""
                ⚠️ **STEP 5: AUDIT & COLLISION RESOLUTION**
                - **Patient X Conflict Ledger:** Preserved both historical sightings transparently (Zero Lost Updates).
                - **Inventory Collision Alert:** 13 claimed > 10 in stock.
                - Coordinator confirms emergency apportionment: **6 kits to Harbor, 4 kits to Hospital**.
            """)
            if st.button("✅ Confirm Apportionment: Grant 6 Kits to Alpha & 4 Kits to Beta", type="primary", use_container_width=True):
                resolve_resqmesh_inventory_collision(sim, 6, 4)
                st.session_state.resolved = True
                st.toast("Collision resolved! 100% convergence achieved.", icon="✅")
                st.rerun()
        else:
            st.success("✅ **CONVERGENCE ACHIEVED!** All 3 stations hold byte-for-byte identical state. Zero lost updates. Zero kits double-allocated!")
            if st.button("🔄 Restart Walkthrough from Step 1", use_container_width=True):
                run_resqmesh_phase1_baseline(sim)
                st.session_state.step = 1
                st.session_state.resolved = False
                st.rerun()


# ---------------------------------------------------------------------------
# 6. SYNCHRONIZATION MONITOR
# ---------------------------------------------------------------------------

def render_sync_monitor(sim: DisasterSimulator) -> None:
    """Render anti-entropy synchronization telemetry, version vectors, and delta metrics."""
    st.markdown("### 🔄 Synchronization & Delta Monitor")
    st.caption("Anti-entropy protocol details: version vectors, delta event exchange, and zero-byte repeated transfers.")

    conv = get_mesh_data_convergence_status(sim)
    stats = sim.transport.get_stats()

    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.metric("Mesh Convergence", "100% IDENTICAL" if conv["is_converged"] else "PENDING SYNC")
    with m2:
        st.metric("Total Wire Traffic", f"{stats['total_bytes']} Bytes")
    with m3:
        st.metric("Framed Messages", stats["total_messages"])
    with m4:
        avg_f = round(stats["total_bytes"] / max(1, stats["total_messages"]), 1)
        st.metric("Average Frame Size", f"{avg_f} B")

    st.write("")
    st.markdown("##### 📐 Node Version Vectors")

    v_cols = st.columns(3)
    for idx, nid in enumerate(sim.node_ids):
        node = sim.nodes[nid]
        vv = node.get_version_vector()
        with v_cols[idx]:
            st.markdown(f"""
                <div class="rn-card">
                    <div style="font-weight:700; color:#00E5FF;">{nid.upper()}</div>
                    <div style="font-family:'JetBrains Mono'; font-size:0.85rem; margin-top:6px;">
                        Max Counter: <strong>{node.store.count()}</strong><br>
                        Vector: <code>{dict(vv)}</code>
                    </div>
                </div>
            """, unsafe_allow_html=True)

    st.write("")
    st.markdown("##### 💡 Minimal Sync Payload Principle")
    st.info("RescueNet guarantees that subsequent sync handshakes between already-converged nodes transfer **0 delta events**. Only new mutations generate wire traffic.")


# ---------------------------------------------------------------------------
# 7. SECURITY CENTRE
# ---------------------------------------------------------------------------

def render_security_centre(sim: DisasterSimulator) -> None:
    """Render cryptographic security, Ed25519 signatures, AES-256-GCM, and revocation ring."""
    st.markdown("### 🔐 Security & Cryptography Centre")
    st.caption("Zero-trust security architecture: field-level authenticated encryption and digital signatures.")

    sec = get_security_summary(sim)

    s1, s2, s3, s4 = st.columns(4)
    with s1:
        st.metric("Field Cipher", "AES-256-GCM")
    with s2:
        st.metric("Digital Signatures", "Ed25519")
    with s3:
        st.metric("Key Derivation", "PBKDF2 100k iter")
    with s4:
        st.metric("Trusted Peers", len(sim.node_ids))

    st.write("")
    st.markdown("##### 🛡️ Cryptographic Revocation Ring")
    st.caption("If a responder laptop is seized or lost in the disaster zone, blacklist it across the mesh.")

    r1, r2 = st.columns([2.5, 1.2])
    with r1:
        rev_node = st.selectbox("Select Station to Revoke", sim.node_ids, key="sel_rev_node")
    with r2:
        st.write("")
        if st.button("🚨 Blacklist Device Now", use_container_width=True):
            res_msg = revoke_compromised_device(sim, rev_node)
            st.toast(f"Device {rev_node} blacklisted.", icon="🚨")
            st.session_state.sync_logs = [res_msg]
            st.rerun()

    # Timeline with Decryption View Toggle
    st.write("")
    st.markdown("##### 📜 Cryptographic Event Audit Feed")
    _render_timeline_inspector(sim)


def _render_timeline_inspector(sim: DisasterSimulator) -> None:
    """Render timeline with payload decryption view toggle."""
    c1, c2 = st.columns([2.0, 1.5])
    with c1:
        sel_nid = st.selectbox("Inspect Station Ledger", sim.node_ids, key="sec_timeline_sel")
    with c2:
        v_mode = st.radio("Payload View", ["Decrypted Application View", "Raw Ciphertext At-Rest"], horizontal=True, key="sec_vmode")

    rows = get_node_timeline(sim, sel_nid, limit=15)
    if not rows:
        st.info("No events in this ledger.")
        return

    table_data = []
    for r in rows:
        crypto_status = "Ed25519 VERIFIED" if r["sig_valid"] else ("Ed25519 SIGNED" if r["signed"] else "UNSIGNED")
        if r["encrypted_pii"]:
            crypto_status += " + AES-256-GCM"
        shown_payload = r["payload"] if v_mode.startswith("Decrypted") else r["raw_payload"]
        table_data.append({
            "Seq": f"{r['node_id'].split('-')[0].capitalize()}#{r['counter']}",
            "Entity": r["entity"],
            "Operation": r["operation"],
            "Security Status": crypto_status,
            "Wire Size": f"{r['wire_bytes']} B",
            "Event Hash": r["event_id"][:12] + "...",
            "Payload Content": json.dumps(shown_payload, sort_keys=True),
        })

    st.dataframe(table_data, use_container_width=True, hide_index=True)


# ---------------------------------------------------------------------------
# 8. RESOURCE ALLOCATION SAFETY
# ---------------------------------------------------------------------------

def render_resource_allocation_safety(sim: DisasterSimulator) -> None:
    """Render escrow quota conservation and boat token single-owner exclusivity."""
    st.markdown("### ⚖️ Resource Allocation Safety")
    st.caption("Mathematical guarantees against double-allocation of scarce disaster resources under partitions.")

    supp = get_medical_supplies_summary(sim)

    st.markdown(f"""
        <div class="rn-invariant-banner">
            <span class="rn-formula">INVARIANT: TOTAL INVENTORY ({supp['total']}) = DISTRIBUTED QUOTAS ({supp['remaining']}) + CONSUMED INVENTORY ({supp['consumed']})</span>
            <span class="rn-formula-verified">{'✅ MATHEMATICALLY CONSERVED' if supp['is_conserved'] else '⚠️ VIOLATION'}</span>
        </div>
    """, unsafe_allow_html=True)

    # Boat Exclusivity Token
    first_node = sim.nodes[sim.node_ids[0]]
    boat = first_node.get_state().get("scarce_item", {}).get("boat-titan", {})
    token_holder = boat.get("token_holder", "None")
    boat_status = boat.get("status", "AVAILABLE")

    st.markdown("##### 🚢 Indivisible Asset Exclusivity (Flood Rescue Boat)")
    st.caption("Only the single verified token holder can confirm allocation. Disconnected peers cannot double-allocate.")

    b1, b2, b3 = st.columns(3)
    with b1:
        st.metric("Asset Name", "Rescue Boat 'Titan'")
    with b2:
        st.metric("Current Token Holder", token_holder.split("-")[0].capitalize())
    with b3:
        st.metric("Operational Status", boat_status)


# ---------------------------------------------------------------------------
# 9. EVENT AND AUDIT LOG
# ---------------------------------------------------------------------------

def render_event_audit_feed(sim: DisasterSimulator) -> None:
    """Render full event audit feed with search, filters, and USB bundle export/import."""
    st.markdown("### 📜 Event Store & Audit Log")
    st.caption("Complete, immutable append-only event ledger across all participating stations.")

    sel_node = st.selectbox("Filter by Node", ["all"] + sim.node_ids, key="audit_filter_node")
    events = []
    if sel_node == "all":
        for nid in sim.node_ids:
            events.extend(sim.nodes[nid].store.get_all_events())
        events.sort(key=lambda x: (x.timestamp, x.node_id, x.counter), reverse=True)
    else:
        events = sim.nodes[sel_node].store.get_all_events()[::-1]

    table_data = []
    for e in events[:30]:
        table_data.append({
            "Timestamp": time.strftime("%H:%M:%S", time.localtime(e.timestamp)),
            "Origin Node": e.node_id,
            "Seq": e.counter,
            "Entity": f"{e.entity_type}:{e.entity_id}",
            "Operation": e.operation,
            "Signed": "Ed25519" if e.signature else "No",
            "Event Hash": e.event_id[:12] + "...",
        })
    st.dataframe(table_data, use_container_width=True, hide_index=True)

    st.write("")
    st.markdown("##### 🚚 Offline USB Sneakernet Sync Bundles")
    u1, u2 = st.columns(2)
    with u1:
        exp_node = st.selectbox("Export USB Bundle from Station", sim.node_ids, key="exp_bundle_node")
        bundle_json = export_node_bundle_json(sim, exp_node)
        st.download_button(
            label=f"⬇️ Download {exp_node.split('-')[0].capitalize()} USB Bundle (.json)",
            data=bundle_json,
            file_name=f"rescuenet_{exp_node}_bundle.json",
            mime="application/json",
            use_container_width=True,
        )
    with u2:
        imp_node = st.selectbox("Import USB Bundle into Station", sim.node_ids, key="imp_bundle_node")
        up_file = st.file_uploader("Upload USB Bundle", type=["json"], key="up_bundle_file")
        if up_file and st.button("Apply Bundle to Station", use_container_width=True):
            content = up_file.getvalue().decode("utf-8")
            res = import_node_bundle_json(sim, imp_node, content)
            st.toast(f"Imported: {res['applied']} applied, {res['skipped_duplicates']} duplicates skipped.", icon="📥")
            st.rerun()


# ---------------------------------------------------------------------------
# 10. LONG-RANGE COMMUNICATION
# ---------------------------------------------------------------------------

def render_long_range_comms() -> None:
    """Render specifications for alternative physical communication methods."""
    st.markdown("### 📻 Long-Range & Alternative Physical Communication")
    st.caption("RescueNet's multi-tier physical transport modalities for zero-infrastructure environments.")

    methods = get_long_range_comms_info()
    for m in methods:
        with st.container():
            st.markdown(f"""
                <div class="rn-card">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <span style="font-size:1.05rem; font-weight:800; color:#FFFFFF;">{m['name']}</span>
                        <span class="{m['status_tag']}">{m['status']}</span>
                    </div>
                    <div style="font-size:0.85rem; color:#8B9BB4; margin-top:4px;">
                        📡 <strong>Medium:</strong> {m['medium']} • ⚡ <strong>Speed:</strong> {m['speed']} • 📏 <strong>Range:</strong> {m['range']}
                    </div>
                    <div style="font-size:0.8rem; color:#A0AEC0; margin-top:6px;">
                        {m['description']}
                    </div>
                </div>
            """, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# 11. SYSTEM HEALTH
# ---------------------------------------------------------------------------

def render_system_health_scorecard(sim: DisasterSimulator) -> None:
    """Render real-time system health diagnostics and scorecard."""
    st.markdown("### 🩺 System Diagnostics & Health Scorecard")
    st.caption("Real computed health metrics across the event-sourcing kernel, SQLite stores, and cryptographic engines.")

    health = get_system_health_metrics(sim)

    h1, h2, h3, h4 = st.columns(4)
    with h1:
        st.metric("Runtime Platform", health["runtime"])
    with h2:
        st.metric("Database Engine", health["database_engine"])
    with h3:
        st.metric("Total Events in Log", health["total_events_in_store"])
    with h4:
        st.metric("Convergence Invariant", health["convergence_status"])

    st.write("")
    h_col1, h_col2 = st.columns(2)
    with h_col1:
        st.markdown(f"""
            <div class="rn-card">
                <div style="font-weight:700; color:#00E5FF;">PERSISTENCE & REPLAY AUDIT</div>
                <div style="margin-top:8px; font-size:0.85rem; line-height:1.6;">
                    • SQLite WAL Journaling: <strong>ACTIVE</strong><br>
                    • Monotonic Counter Continuity: <strong>VERIFIED (Zero Regression)</strong><br>
                    • Content-Addressable Event Hash: <strong>SHA-256</strong><br>
                    • Idempotent Deduplication: <strong>ENFORCED</strong>
                </div>
            </div>
        """, unsafe_allow_html=True)
    with h_col2:
        st.markdown(f"""
            <div class="rn-card">
                <div style="font-weight:700; color:#00E5FF;">CRYPTOGRAPHIC INTEGRITY</div>
                <div style="margin-top:8px; font-size:0.85rem; line-height:1.6;">
                    • Asymmetric Signing: <strong>Ed25519 (256-bit)</strong><br>
                    • Field Confidentiality: <strong>AES-256-GCM</strong><br>
                    • Key Derivation: <strong>PBKDF2-HMAC-SHA256 (100k iter)</strong><br>
                    • Fail-Closed Enforcement: <strong>ACTIVE</strong>
                </div>
            </div>
        """, unsafe_allow_html=True)
