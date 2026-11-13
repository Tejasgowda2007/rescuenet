"""
UI Components for RescueNet Disaster Operations Center Dashboard.
Provides modular renderers for Header, Controls Bar, Station Cards, and Actions.
"""

from __future__ import annotations
import json
import time
from typing import Any, Dict, List
import streamlit as st
from simulator.engine import DisasterSimulator
from allocation.escrow import EscrowManager, InsufficientQuotaError
from allocation.tokens import TokenManager, UnauthorizedAllocationError
from ui.controller import (
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
)


NODE_METADATA: List[Dict[str, str]] = [
    {
        "id": "alpha-harbor",
        "title": "Alpha: Coast Guard Harbor",
        "icon": "⚓",
        "role": "Command Post & Primary Logistics Depot",
        "card_class": "station-card-alpha",
        "accent": "#2563EB",
    },
    {
        "id": "beta-hospital",
        "title": "Beta: Field Trauma Clinic",
        "icon": "🏥",
        "role": "Emergency Medical Center & Triage",
        "card_class": "station-card-beta",
        "accent": "#0D9488",
    },
    {
        "id": "gamma-mountain",
        "title": "Gamma: Mountain Shelter Relay",
        "icon": "⛰️",
        "role": "Highland Evacuation Camp & Radio Relay",
        "card_class": "station-card-gamma",
        "accent": "#7C3AED",
    },
]


def render_header(sim: DisasterSimulator) -> None:
    """Render top operational header with real computed network and convergence status pills."""
    conn = get_mesh_connectivity_status(sim)
    conv = get_mesh_data_convergence_status(sim)
    crypto_on = st.session_state.get("crypto_enabled", True)
    total_wire_bytes = sim.transport.get_stats().get("total_bytes", 0)

    conn_class = "rn-pill-connected" if conn["is_connected"] else "rn-pill-split"
    conv_class = "rn-pill-converged" if conv["is_converged"] else "rn-pill-diverged"
    crypto_label = "Ed25519 + AES-256-GCM Active" if crypto_on else "Plaintext Mode"

    st.markdown(f"""
        <div class="rn-header">
            <div class="rn-header-top">
                <div class="rn-title-group">
                    <div class="rn-title">
                        <span>📡 RescueNet Command Center</span>
                    </div>
                    <div class="rn-tagline">
                        Offline Disaster Coordination — Zero Internet, Zero Central Servers, Zero Data Loss
                    </div>
                </div>
            </div>
            <div class="rn-pills-row">
                <span class="rn-badge-sim">⚡ Simulated In-Memory Network</span>
                <span class="{conn_class}">{conn['icon']} Network: {conn['label']}</span>
                <span class="{conv_class}">{conv['icon']} Data: {conv['label']}</span>
                <span class="rn-pill-connected">🔐 {crypto_label}</span>
                <span class="rn-badge-sim" style="border-color:#38BDF8; color:#38BDF8; background:rgba(56,189,248,0.12);">
                    📦 Wire: {total_wire_bytes} B
                </span>
            </div>
        </div>
    """, unsafe_allow_html=True)


def render_controls_bar(sim: DisasterSimulator, reset_callback: Any) -> None:
    """
    Render main control bar with state-aware button disabling and explanatory tooltips.
    """
    conn = get_mesh_connectivity_status(sim)
    is_connected = conn["is_connected"]
    comps = conn["components"]
    is_gamma_cut = (len(comps) == 2 and ["gamma-mountain"] in comps)

    c1, c2, c3, c4, c5, c6 = st.columns([1.1, 1.2, 1.2, 1.3, 1.4, 1.1])

    with c1:
        if st.button("🧹 Reset", use_container_width=True, help="Reset mesh to clean, fully-converged baseline (< 2s)"):
            reset_callback()
            st.toast("Mesh reset to clean initial baseline.", icon="🧹")
            st.rerun()

    with c2:
        cut_disabled = is_gamma_cut
        cut_help = "Gamma is already isolated from Alpha and Beta" if cut_disabled else "Isolate Gamma Mountain Shelter (simulate hurricane cut)"
        if st.button("🔴 Cut Mountain", disabled=cut_disabled, help=cut_help, use_container_width=True):
            cut_network_partition(sim)
            st.session_state.sync_logs = ["Partition Applied: Gamma Mountain Shelter isolated from Alpha & Beta."]
            st.toast("Mountain station partitioned from harbor and hospital.", icon="🔴")
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
            st.toast(f"Mesh sync finished ({len(results)} pairwise exchanges).", icon="🔄")
            st.rerun()

    with c5:
        if st.button("⚡ Inject Conflict", use_container_width=True, help="Record competing observations of Dr. Stone on Alpha and Gamma"):
            inject_conflicting_doctor_sightings(sim)
            st.session_state.sync_logs = ["Concurrent conflict injected: Dr. Stone reported MISSING at Pier 14 vs FOUND at Mountain Shelter."]
            st.toast("Concurrent conflicting doctor sightings recorded!", icon="⚡")
            st.rerun()

    with c6:
        curr_crypto = st.session_state.get("crypto_enabled", True)
        label = "🔓 Plain" if curr_crypto else "🔐 Ed25519"
        help_text = "Switch to plaintext simulation" if curr_crypto else "Enable Ed25519 signing & AES-256-GCM encryption"
        if st.button(label, use_container_width=True, help=help_text):
            st.session_state.crypto_enabled = not curr_crypto
            reset_callback()
            st.toast(f"Security mode switched: {'Ed25519 + AES' if not curr_crypto else 'Plaintext'}", icon="🔐")
            st.rerun()

    # Presets row
    p1, p2, p3, p_info = st.columns([1.2, 1.2, 1.2, 2.0])
    with p1:
        if st.button("🌊 Flash Flood Preset", use_container_width=True, help="Isolates Gamma, logs boat claim, consumes medical escrow"):
            st.session_state.sync_logs = run_scenario_preset(sim, "flash_flood")
            st.toast("Flash Flood scenario applied.", icon="🌊")
            st.rerun()
    with p2:
        if st.button("💊 Supply Rebalance", use_container_width=True, help="Isolates Alpha, transfers 15 antibiotic courses Gamma -> Beta"):
            st.session_state.sync_logs = run_scenario_preset(sim, "supply_crunch")
            st.toast("Supply rebalance scenario applied.", icon="💊")
            st.rerun()
    with p3:
        if st.button("🔁 2-Hop Relay Mule", use_container_width=True, help="Cuts Alpha-Gamma link, routing messages through Beta"):
            st.session_state.sync_logs = run_scenario_preset(sim, "chain_mule")
            st.toast("2-hop chain relay scenario applied.", icon="🔁")
            st.rerun()
    with p_info:
        if st.session_state.get("sync_logs"):
            latest_log = st.session_state.sync_logs[-1]
            st.caption(f"**Latest Activity:** {latest_log}")


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
        # Station Card Container
        st.markdown(f"""
            <div class="station-card {cfg['card_class']}">
                <div class="station-header">
                    <div>
                        <div class="station-title">{cfg['icon']} {cfg['title']}</div>
                        <div class="station-role">{cfg['role']}</div>
                    </div>
                    <div>
                        <span class="{sync_info['badge_class']}">{sync_info['icon']} {sync_info['label']}</span>
                    </div>
                </div>
            </div>
        """, unsafe_allow_html=True)

        # Plain-English Version Vector Box
        st.markdown(f"""
            <div class="vv-box">
                <strong>Data Sync:</strong> {vv_plain}
            </div>
        """, unsafe_allow_html=True)

        with st.expander("Technical Vector Details", expanded=False):
            st.write(f"**Local SQLite Events:** `{node.store.count()}`")
            st.write(f"**Raw Version Vector:** `{dict(raw_vv)}`")

        # Resource Meters Section
        m_col1, m_col2 = st.columns(2)
        with m_col1:
            st.markdown(f"""
                <div class="meter-card">
                    <div class="meter-title">
                        <span>💊 Antibiotics Quota</span>
                        <span style="color:{meters['quota_color']};">{meters['my_quota']}/{meters['total_quantity']}</span>
                    </div>
                </div>
            """, unsafe_allow_html=True)
            st.progress(min(1.0, max(0.0, meters["quota_ratio"])))
            st.caption(f"Status: **{meters['quota_status']}** (Consumed: {meters['consumed']})")

        with m_col2:
            if meters["has_token"]:
                alloc_msg = f" (Mission: {meters['allocated_to']})" if meters["allocated_to"] else " (Ready)"
                st.markdown(f"""
                    <div class="token-badge-active">
                        🚢 <strong>Boat Token Held</strong>{alloc_msg}
                    </div>
                """, unsafe_allow_html=True)
            else:
                holder_short = meters["token_holder"].split("-")[0].capitalize() if meters["token_holder"] else "None"
                st.markdown(f"""
                    <div class="token-badge-inactive">
                        ⚓ Token Holder: {holder_short}
                    </div>
                """, unsafe_allow_html=True)
            if meters["has_pending_request"]:
                st.caption("⏳ Offline request queued for sync.")

        # Action Tabs
        with st.expander(f"⚡ Field Actions ({cfg['id'].split('-')[0].capitalize()})", expanded=True):
            tab_person, tab_supplies, tab_boat, tab_shelter = st.tabs(["Person", "Supplies", "Boat", "Shelter / Need"])

            # 1. Person Sighting Form
            with tab_person:
                with st.form(key=f"form_person_{nid}"):
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
                        st.toast(f"{cfg['title'].split(':')[0]} logged update for {p_name} ({p_status})", icon="👤")
                        st.rerun()

            # 2. Supplies Form (Consume or Transfer)
            with tab_supplies:
                st.write(f"**Local Quota:** `{meters['my_quota']}` courses")
                s_action = st.radio("Supply Action", ["Consume from Local Quota", "Transfer Quota to Station"], key=f"s_act_{nid}", horizontal=True)

                if s_action == "Consume from Local Quota":
                    with st.form(key=f"form_consume_{nid}"):
                        c_qty = st.number_input("Quantity to Consume", min_value=1, max_value=max(1, meters['my_quota']), value=min(4, max(1, meters['my_quota'])))
                        c_for = st.text_input("Patient / Reason", value="Critical care patient")
                        if st.form_submit_button("Consume Courses", use_container_width=True):
                            try:
                                EscrowManager.consume(node, "supply-antibiotics", int(c_qty), c_for)
                                st.toast(f"Consumed {c_qty} antibiotics at {cfg['title'].split(':')[0]}.", icon="💊")
                                st.rerun()
                            except InsufficientQuotaError as exc:
                                st.error(f"Cannot consume: {exc}")
                else:
                    with st.form(key=f"form_transfer_{nid}"):
                        t_target = st.selectbox("Recipient Station", peer_ids, key=f"t_target_{nid}")
                        t_qty = st.number_input("Quantity to Transfer", min_value=1, max_value=max(1, meters['my_quota']), value=min(5, max(1, meters['my_quota'])))
                        t_reason = st.text_input("Transfer Reason", value="Field quota rebalance")
                        if st.form_submit_button("Transfer Quota", use_container_width=True):
                            try:
                                EscrowManager.transfer_quota(node, t_target, "supply-antibiotics", int(t_qty), t_reason)
                                st.toast(f"Transferred {t_qty} quota to {t_target.split('-')[0]}.", icon="🚚")
                                st.rerun()
                            except InsufficientQuotaError as exc:
                                st.error(f"Cannot transfer: {exc}")

            # 3. Boat Token Form
            with tab_boat:
                if meters["has_token"] and meters["boat_status"] == "AVAILABLE":
                    st.success("You hold the boat token. The boat is currently available.")
                    with st.form(key=f"form_alloc_boat_{nid}"):
                        b_mission = st.text_input("Mission Name", value=f"Evacuation Run ({nid.split('-')[0].title()})")
                        if st.form_submit_button("Confirm Boat Deployment", use_container_width=True):
                            try:
                                TokenManager.confirm_allocation(node, "boat-titan", b_mission, nid)
                                st.toast(f"Boat allocated to mission: {b_mission}", icon="🚢")
                                st.rerun()
                            except UnauthorizedAllocationError as exc:
                                st.error(str(exc))

                    with st.form(key=f"form_xfer_boat_{nid}"):
                        b_target = st.selectbox("Hand Off Token Custody To", peer_ids, key=f"bx_{nid}")
                        if st.form_submit_button("Transfer Token Custody", use_container_width=True):
                            try:
                                TokenManager.transfer_token(node, "boat-titan", b_target, "Custody handoff")
                                st.toast(f"Boat token custody transferred to {b_target}.", icon="🤝")
                                st.rerun()
                            except UnauthorizedAllocationError as exc:
                                st.error(str(exc))

                elif meters["has_token"] and meters["boat_status"] == "CONFIRMED_ALLOCATED":
                    st.warning(f"Boat is deployed on mission: **{meters['allocated_to']}**")
                    if st.button("Mark Mission Complete & Release Boat", key=f"rel_b_{nid}", use_container_width=True):
                        TokenManager.release_item(node, "boat-titan", notes="Mission completed safely")
                        st.toast("Boat released back to available pool.", icon="✅")
                        st.rerun()
                else:
                    holder_name = meters['token_holder'].split('-')[0].capitalize() if meters['token_holder'] else 'Unknown'
                    st.info(f"Token held by **{holder_name}**. You can submit an offline request.")
                    with st.form(key=f"form_req_boat_{nid}"):
                        b_req_mission = st.text_input("Request Purpose", value=f"Emergency extraction near {nid.split('-')[1].title()}")
                        if st.form_submit_button("Submit Offline Request", use_container_width=True):
                            TokenManager.request_allocation(node, "boat-titan", b_req_mission)
                            st.toast("Offline boat allocation request queued.", icon="📝")
                            st.rerun()

            # 4. Shelter & Emergency Needs
            with tab_shelter:
                with st.form(key=f"form_sh_{nid}"):
                    sh_name = st.text_input("Shelter Facility", value=f"{nid.split('-')[0].title()} Relief Camp")
                    sh_id = "shelter-" + sh_name.lower().replace(" ", "-")
                    sh_occ = st.number_input("Current Occupancy", min_value=0, max_value=1000, value=30)
                    sh_cap = st.number_input("Max Capacity", min_value=1, max_value=1000, value=100)
                    if st.form_submit_button("Log Shelter Update", use_container_width=True):
                        node.record_event("shelter", sh_id, "UPDATE", {"name": sh_name, "occupancy": int(sh_occ), "capacity": int(sh_cap)})
                        st.toast(f"Shelter {sh_name} updated ({sh_occ}/{sh_cap}).", icon="⛺")
                        st.rerun()

                with st.form(key=f"form_need_{nid}"):
                    n_item = st.text_input("Emergency Need Description", value="Portable Generator Fuel (100L)")
                    n_urg = st.selectbox("Urgency Level", ["CRITICAL", "HIGH", "MEDIUM"])
                    if st.form_submit_button("Post Urgent Need", use_container_width=True):
                        need_id = f"need-{nid.split('-')[0]}-{int(time.time() * 1000) % 10000}"
                        node.record_event("need", need_id, "CREATE", {"item": n_item, "urgency": n_urg})
                        st.toast(f"Posted {n_urg} need: {n_item}", icon="🚨")
                        st.rerun()

        # Compact Local Records View
        with st.expander("📋 View Station Local Records", expanded=False):
            people = state.get("person", {})
            if people:
                st.write("**People Records:**")
                for pid, pdata in people.items():
                    c_tag = " [⚠️ DISPUTED]" if pdata.get("conflicts") else ""
                    st.write(f"• **{pdata.get('name', pid)}**: `{pdata.get('status')}` @ {pdata.get('location', 'N/A')}{c_tag}")

            shelters = state.get("shelter", {})
            if shelters:
                st.write("**Shelter Capacities:**")
                for _, sdata in shelters.items():
                    st.write(f"• **{sdata.get('name')}**: {sdata.get('occupancy', 0)}/{sdata.get('capacity', 0)}")

            needs = state.get("need", {})
            if needs:
                st.write("**Emergency Needs:**")
                for _, ndata in list(needs.items())[-4:]:
                    status_str = "RESOLVED" if ndata.get("status") == "RESOLVED" else ndata.get("urgency")
                    st.write(f"• **{ndata.get('item')}** ({status_str})")
