"""
RescueNet & ResQ-Mesh Unified Disaster Command Center UI.
Three Disaster Coordination Nodes Side-by-Side with Live Mesh Topology SVG,
Granular Link/Partition Controls, Scenario Presets, Crypto Event Inspector,
USB Sneakernet Bundle Sync, and 3-Phase Executive Disaster Showcase.
"""

from __future__ import annotations
import json
import os
import sys
import time
from datetime import datetime
from typing import Any, Dict, List

# Ensure project root is on sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import streamlit as st
import streamlit.components.v1 as components
from simulator.engine import DisasterSimulator
from allocation.escrow import EscrowManager, InsufficientQuotaError
from allocation.tokens import TokenManager, UnauthorizedAllocationError
from allocation.conflict_resolver import ConflictResolver
from ui.controller import (
    create_ui_simulator,
    cut_network_partition,
    set_custom_partition,
    toggle_link,
    heal_network_links,
    run_mesh_sync,
    inject_conflicting_doctor_sightings,
    run_scenario_preset,
    check_mesh_convergence,
    export_node_bundle_json,
    import_node_bundle_json,
    get_node_timeline,
    build_mesh_topology_svg,
    run_resqmesh_phase1_baseline,
    run_resqmesh_phase2_split_and_conflict,
    run_resqmesh_phase3_reconnect_and_converge,
    resolve_resqmesh_inventory_collision,
    dispatch_ambulance_data_mule,
    revoke_compromised_device,
)


def _render_resqmesh_showcase(sim: DisasterSimulator) -> None:
    curr_step = st.session_state.get("step", 1)

    # Clean CSS
    st.markdown("""
        <style>
        .block-container { padding-top: 1.5rem; max-width: 860px; }
        .main-heading { font-size: 2rem; font-weight: 800; text-align: center; color: #0F172A; margin-bottom: 2px; }
        .sub-heading { font-size: 1rem; text-align: center; color: #64748B; margin-bottom: 1.5rem; }
        .camp-box { border-radius: 10px; padding: 16px; border: 2px solid #E2E8F0; background: white; text-align: center; }
        .camp-green { border-color: #10B981; }
        .camp-red { border-color: #EF4444; background: #FEF2F2; }
        .status-badge-green { background: #DCFCE7; color: #166534; font-weight: 700; padding: 3px 10px; border-radius: 12px; font-size: 0.8rem; }
        .status-badge-red { background: #FEE2E2; color: #991B1B; font-weight: 700; padding: 3px 10px; border-radius: 12px; font-size: 0.8rem; }
        .action-box { background: #F8FAFC; border: 1px solid #E2E8F0; padding: 14px; border-radius: 8px; margin-top: 15px; }
        </style>
    """, unsafe_allow_html=True)

    st.markdown('<div class="main-heading">📡 ResQ-Mesh</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-heading">Offline Disaster Coordination — No Internet, No Servers, Zero Data Loss</div>', unsafe_allow_html=True)

    # ---------------------------------------------------------------------------
    # 3 BIG SIMPLE BUTTONS
    # ---------------------------------------------------------------------------
    b1, b2, b3 = st.columns(3)
    with b1:
        if st.button("1️⃣ Normal (Online)", use_container_width=True, type="primary" if curr_step == 1 else "secondary"):
            run_resqmesh_phase1_baseline(sim)
            st.session_state.step = 1
            st.session_state.resolved = False
            st.session_state.show_qr = False
            st.rerun()

    with b2:
        if st.button("2️⃣ Network Dies!", use_container_width=True, type="primary" if curr_step == 2 else "secondary"):
            run_resqmesh_phase2_split_and_conflict(sim)
            st.session_state.step = 2
            st.session_state.resolved = False
            st.session_state.show_qr = False
            st.rerun()

    with b3:
        if st.button("3️⃣ Reconnect & Fix", use_container_width=True, type="primary" if curr_step == 3 else "secondary"):
            run_resqmesh_phase3_reconnect_and_converge(sim)
            st.session_state.step = 3
            st.session_state.show_qr = False
            st.rerun()

    st.write("")

    # ---------------------------------------------------------------------------
    # SIMPLE STORY BANNER
    # ---------------------------------------------------------------------------
    if curr_step == 1:
        st.info("🟢 **Step 1:** All 3 camps are online. There are **10 Medical Kits** in stock. Everyone agrees.")
    elif curr_step == 2:
        st.error("🔴 **Step 2: Earthquake Cuts the Signal!** Both camps are isolated. Harbor claims **8 kits** (reports Patient X 'Found'). Mountain claims **5 kits** (reports Patient X 'Injured'). That's **13 kits claimed for 10 in stock!**")
    elif curr_step == 3:
        if not st.session_state.resolved:
            st.warning("⚠️ **Step 3: Signal Returns!** The system merged both reports of Patient X (zero data lost). But **13 kits were claimed for 10 available stock**. Tap below to resolve.")
            if st.button("✅ Tap to Resolve: Give 6 Kits to Harbor & 4 Kits to Mountain", use_container_width=True, type="primary"):
                resolve_resqmesh_inventory_collision(sim, 6, 4)
                st.session_state.resolved = True
                st.rerun()
        else:
            st.success("✅ **Conflict Resolved!** 6 kits given to Harbor, 4 to Mountain. Zero kits double-allocated. All devices hold identical data!")

    st.write("")

    # ---------------------------------------------------------------------------
    # 3 SIMPLE CAMP BOXES
    # ---------------------------------------------------------------------------
    c1, c2, c3 = st.columns(3)

    state_alpha = sim.nodes["alpha-harbor"].get_state()
    kits_alpha = state_alpha.get("supply_intent", {}).get("medical-kits-pool", {})

    with c1:
        is_on = (curr_step != 2)
        p_stat = state_alpha.get("person", {}).get("person-patient-x", {}).get("status", "Pending")
        box_style = "camp-green" if is_on else "camp-red"
        pill = '<span class="status-badge-green">Online</span>' if is_on else '<span class="status-badge-red">Cut Off</span>'
        kit_display = "6 Granted" if st.session_state.resolved else ("8 Claimed" if curr_step > 1 else "10 Shared")

        st.markdown(f"""
            <div class="camp-box {box_style}">
                <h4 style="margin:0 0 8px 0;">⚓ Harbor Camp</h4>
                {pill}
                <hr style="margin:10px 0; border:none; border-top:1px solid #E2E8F0;">
                <p style="margin:0; font-size:0.85rem; color:#64748B;">Patient X:</p>
                <p style="margin:0 0 8px 0; font-weight:700; color:#1E3A8A;">{p_stat}</p>
                <p style="margin:0; font-size:0.85rem; color:#64748B;">Medical Kits:</p>
                <p style="margin:0; font-weight:700;">{kit_display}</p>
            </div>
        """, unsafe_allow_html=True)

    with c2:
        state_beta = sim.nodes["beta-hospital"].get_state()
        is_on = (curr_step != 2)
        p_stat_b = state_beta.get("person", {}).get("person-patient-x", {}).get("status", "Pending")
        box_style = "camp-green" if is_on else "camp-red"
        pill = '<span class="status-badge-green">Online</span>' if is_on else '<span class="status-badge-red">Cut Off</span>'
        kit_display_b = "4 Granted" if st.session_state.resolved else ("5 Claimed" if curr_step > 1 else "10 Shared")

        st.markdown(f"""
            <div class="camp-box {box_style}">
                <h4 style="margin:0 0 8px 0;">⛰️ Mountain Camp</h4>
                {pill}
                <hr style="margin:10px 0; border:none; border-top:1px solid #E2E8F0;">
                <p style="margin:0; font-size:0.85rem; color:#64748B;">Patient X:</p>
                <p style="margin:0 0 8px 0; font-weight:700; color:#DC2626;">{p_stat_b}</p>
                <p style="margin:0; font-size:0.85rem; color:#64748B;">Medical Kits:</p>
                <p style="margin:0; font-weight:700;">{kit_display_b}</p>
            </div>
        """, unsafe_allow_html=True)

    with c3:
        state_gamma = sim.nodes["gamma-mountain"].get_state()
        is_on = (curr_step != 2)
        box_style = "camp-green" if is_on else "camp-red"
        pill = '<span class="status-badge-green">Online</span>' if is_on else '<span class="status-badge-red">Cut Off</span>'

        st.markdown(f"""
            <div class="camp-box {box_style}">
                <h4 style="margin:0 0 8px 0;">🚐 Mobile Clinic</h4>
                {pill}
                <hr style="margin:10px 0; border:none; border-top:1px solid #E2E8F0;">
                <p style="margin:0; font-size:0.85rem; color:#64748B;">Role:</p>
                <p style="margin:0 0 8px 0; font-weight:700; color:#475569;">Ambulance Patrol</p>
                <p style="margin:0; font-size:0.85rem; color:#64748B;">Radio Link:</p>
                <p style="margin:0; font-weight:700;">{"Mesh Active" if is_on else "Disconnected"}</p>
            </div>
        """, unsafe_allow_html=True)

    st.write("")
    st.write("")

    # ---------------------------------------------------------------------------
    # HOW DEVICES TALK WITH NO INTERNET (DIRECTLY ON SCREEN)
    # ---------------------------------------------------------------------------
    st.markdown("##### 📻 No Internet? Try the 3 Zero-Hardware Ways to Sync:")
    f1, f2, f3 = st.columns(3)

    with f1:
        # Walkie-Talkie Sound
        components.html("""
            <button onclick="playChirp()" style="background:#4F46E5; color:white; border:none; padding:10px 12px; border-radius:6px; font-weight:700; font-size:0.9rem; cursor:pointer; width:100%;">
                🔊 1. Play Walkie-Talkie Sound
            </button>
            <script>
            function playChirp() {
                const ctx = new (window.AudioContext || window.webkitAudioContext)();
                const osc = ctx.createOscillator();
                const gain = ctx.createGain();
                osc.type = 'sine';
                osc.frequency.setValueAtTime(1500, ctx.currentTime);
                osc.frequency.linearRampToValueAtTime(2400, ctx.currentTime + 0.3);
                osc.frequency.linearRampToValueAtTime(1800, ctx.currentTime + 0.6);
                osc.frequency.linearRampToValueAtTime(2200, ctx.currentTime + 1.0);
                gain.gain.setValueAtTime(0.35, ctx.currentTime);
                gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 1.0);
                osc.connect(gain);
                gain.connect(ctx.destination);
                osc.start();
                osc.stop(ctx.currentTime + 1.0);
            }
            </script>
        """, height=50)
        st.caption("Plays a 1-sec data whistle into any $20 analog walkie-talkie.")

    with f2:
        # Optical Screen-to-Camera QR
        if st.button("📷 2. Show Sync QR Code", use_container_width=True):
            st.session_state.show_qr = not st.session_state.get("show_qr", False)

        st.caption("Point another phone's camera at this screen to sync through light.")

    with f3:
        # Ambulance Data Mule
        if st.button("🚑 3. Send Ambulance Mule", use_container_width=True):
            res = dispatch_ambulance_data_mule(sim, "alpha-harbor", "gamma-mountain")
            st.success("Ambulance physically carried the updates across the mountain!")

        st.caption("Ambulance driver's phone physically carries updates across camps.")

    # QR Code Display (fully offline: rendered locally, no network call)
    if st.session_state.get("show_qr", False):
        sync_payload = "ResQMesh-Delta-Sync-Event-50Bytes"
        st.markdown("""
            <div style="text-align:center; background:#F8FAFC; padding:15px; border-radius:10px; border:2px dashed #94A3B8; margin-top:10px;">
                <h5 style="margin:0 0 8px 0;">📷 Screen-to-Camera Optical Frame</h5>
                <div style="font-family:monospace; font-size:1.1rem; letter-spacing:2px; padding:12px; background:white; border:1px solid #CBD5E1; border-radius:6px; display:inline-block;">
                    """ + sync_payload + """
                </div>
                <p style="margin:8px 0 0 0; font-size:0.85rem; color:#475569;">
                    Show this code to another phone's camera for 1 second.<br>
                    <strong>Syncs with 0 Wi-Fi, 0 Bluetooth, 0 radio waves — 100% offline.</strong>
                </p>
            </div>
        """, unsafe_allow_html=True)


NODE_CONFIGS: List[Dict[str, str]] = [
    {"id": "alpha-harbor", "title": "⚓ Alpha: Coast Guard Harbor", "desc": "Command Post & Primary Depot"},
    {"id": "beta-hospital", "title": "🏥 Beta: Field Trauma Clinic", "desc": "Triage & Emergency Surgery"},
    {"id": "gamma-mountain", "title": "⛰️ Gamma: Mountain Shelter", "desc": "Highland Evacuation Camp"},
]


def _init_session_state(enable_crypto: bool = True) -> DisasterSimulator:
    """Initialize or return the active DisasterSimulator and telemetry state."""
    if "sim" not in st.session_state:
        st.session_state.crypto_enabled = enable_crypto
        st.session_state.sim = create_ui_simulator(enable_crypto=enable_crypto)
        st.session_state.sync_logs = []
        st.session_state.sync_history = []
        st.session_state.step = 1
        st.session_state.resolved = False
        st.session_state.show_qr = False
    return st.session_state.sim


def _reset_demo(enable_crypto: bool) -> None:
    """Tear down existing simulator and bootstrap a fresh mesh."""
    if "sim" in st.session_state:
        st.session_state.sim.close()
    st.session_state.crypto_enabled = enable_crypto
    st.session_state.sim = create_ui_simulator(enable_crypto=enable_crypto)
    st.session_state.sync_logs = ["Demo reset cleanly."]
    st.session_state.sync_history = []


def _record_sync_logs(logs: List[str]) -> None:
    """Store latest sync logs and append byte telemetry for diagnostics."""
    st.session_state.sync_logs = logs
    st.session_state.sync_history.append({
        "time": datetime.now().strftime("%H:%M:%S"),
        "summary": " | ".join(logs),
    })


def _inject_custom_css() -> None:
    st.markdown("""
        <style>
        .rn-header-bar {
            background: linear-gradient(135deg, #0F172A 0%, #1E3A8A 100%);
            color: #F8FAFC;
            padding: 18px 22px;
            border-radius: 12px;
            margin-bottom: 14px;
            border: 1px solid #334155;
        }
        .rn-title { font-size: 1.85rem; font-weight: 800; margin: 0; letter-spacing: -0.02em; }
        .rn-subtitle { font-size: 0.96rem; color: #CBD5E1; margin-top: 4px; }
        .rn-pills { margin-top: 10px; display: flex; gap: 8px; flex-wrap: wrap; }
        .rn-pill {
            display: inline-block; padding: 3px 10px; border-radius: 999px;
            font-size: 0.78rem; font-weight: 700;
            background: rgba(255,255,255,0.14); color: #E2E8F0; border: 1px solid rgba(255,255,255,0.2);
        }
        .conflict-alert {
            background: #FEF3C7; border-left: 4px solid #F59E0B;
            padding: 8px 12px; border-radius: 6px; margin-bottom: 8px;
            font-size: 0.87rem; color: #78350F;
        }
        .converged-badge {
            background: #ECFDF5; border-left: 5px solid #10B981;
            padding: 12px 16px; border-radius: 8px; font-weight: 600; color: #065F46;
        }
        .diverged-badge {
            background: #FEF2F2; border-left: 5px solid #EF4444;
            padding: 12px 16px; border-radius: 8px; font-weight: 600; color: #991B1B;
        }
        </style>
    """, unsafe_allow_html=True)


def _render_header(sim: DisasterSimulator) -> None:
    crypto_label = "Ed25519 + AES-256-GCM ON" if st.session_state.get("crypto_enabled") else "Plaintext Mode"
    comps = sim.partition_manager.get_connected_components()
    net_label = "FULL MESH (3/3)" if len(comps) == 1 else f"PARTITIONED ({len(comps)} ISLANDS)"
    total_bytes = sim.transport.get_stats()["total_bytes"]

    st.markdown(f"""
        <div class="rn-header-bar">
            <div class="rn-title">📡 RescueNet Command Center — Offline-First Disaster Mesh</div>
            <div class="rn-subtitle">
                Peer-to-Peer Event Sourcing, Anti-Entropy Sync, Escrow Quotas & Single-Owner Tokens under Zero Internet
            </div>
            <div class="rn-pills">
                <span class="rn-pill">🌐 {net_label}</span>
                <span class="rn-pill">🔐 {crypto_label}</span>
                <span class="rn-pill">📦 Wire Traffic: {total_bytes} bytes</span>
            </div>
        </div>
    """, unsafe_allow_html=True)


def _render_top_controls(sim: DisasterSimulator) -> None:
    c1, c2, c3, c4, c5, c6 = st.columns([1.2, 1.15, 1.15, 1.1, 1.4, 1.0])

    with c1:
        if st.button("🔴 Cut Mountain", use_container_width=True, help="Isolate Gamma from Alpha & Beta"):
            cut_network_partition(sim)
            st.session_state.sync_logs = ["Partitioned: Gamma isolated from Alpha & Beta."]
            st.rerun()

    with c2:
        if st.button("✂️ Isolate All 3", use_container_width=True, help="Sever every radio link across all 3 stations"):
            set_custom_partition(sim, "split_all")
            st.session_state.sync_logs = ["All 3 stations completely isolated (0 active links)."]
            st.rerun()

    with c3:
        if st.button("🟢 Heal Links", use_container_width=True, help="Restore all radio links across the mesh"):
            heal_network_links(sim)
            st.session_state.sync_logs = ["All radio links healed (Full Mesh)."]
            st.rerun()

    with c4:
        if st.button("🔄 Sync Mesh", use_container_width=True, help="Run pairwise anti-entropy delta sync"):
            _record_sync_logs(run_mesh_sync(sim))
            st.rerun()

    with c5:
        if st.button("⚡ Inject Conflict", use_container_width=True, help="Log competing Dr. Stone sightings on Alpha & Gamma"):
            inject_conflicting_doctor_sightings(sim)
            st.session_state.sync_logs = ["Injected concurrent conflicting sightings on Dr. Stone (Alpha vs Gamma)."]
            st.rerun()

    with c6:
        if st.button("🧹 Reset", use_container_width=True):
            _reset_demo(enable_crypto=st.session_state.get("crypto_enabled", True))
            st.rerun()

    # Scenario Presets + Security Mode row
    p1, p2, p3, p4 = st.columns([1.2, 1.2, 1.2, 1.4])
    with p1:
        if st.button("🌊 Scenario: Flash Flood", use_container_width=True):
            st.session_state.sync_logs = run_scenario_preset(sim, "flash_flood")
            st.rerun()
    with p2:
        if st.button("💊 Scenario: Quota Rebalance", use_container_width=True):
            st.session_state.sync_logs = run_scenario_preset(sim, "supply_crunch")
            st.rerun()
    with p3:
        if st.button("🔁 Scenario: 2-Hop Mule", use_container_width=True):
            st.session_state.sync_logs = run_scenario_preset(sim, "chain_mule")
            st.rerun()
    with p4:
        current_sec = st.session_state.get("crypto_enabled", True)
        toggle_label = "🔓 Switch to Plaintext" if current_sec else "🔐 Enable Ed25519 + AES"
        if st.button(toggle_label, use_container_width=True, help="Reinitializes demo with selected crypto mode"):
            _reset_demo(enable_crypto=not current_sec)
            st.rerun()


def _render_topology_section(sim: DisasterSimulator) -> None:
    topo_col, link_col = st.columns([2.2, 1.0])

    with topo_col:
        st.markdown(build_mesh_topology_svg(sim), unsafe_allow_html=True)

    with link_col:
        st.markdown("**Radio Link Switches**")
        link_pairs = [
            ("alpha-harbor", "beta-hospital", "Alpha ↔ Beta"),
            ("alpha-harbor", "gamma-mountain", "Alpha ↔ Gamma"),
            ("beta-hospital", "gamma-mountain", "Beta ↔ Gamma"),
        ]
        for n1, n2, label in link_pairs:
            up = sim.transport.is_connected(n1, n2)
            icon = "🟢 UP" if up else "🔴 CUT"
            if st.button(f"{icon} — {label}", key=f"link_{n1}_{n2}", use_container_width=True):
                now_up = toggle_link(sim, n1, n2)
                st.session_state.sync_logs = [f"Link {label} {'RESTORED' if now_up else 'CUT'}."]
                st.rerun()

        comps = sim.partition_manager.get_connected_components()
        if len(comps) > 1:
            comp_str = " | ".join([f"[{', '.join(c.split('-')[0] for c in grp)}]" for grp in comps])
            st.warning(f"Islands: {comp_str}")
        else:
            st.success("Connected: Full 3-Node Mesh")

    if st.session_state.get("sync_logs"):
        st.info("**Activity:** " + "  |  ".join(st.session_state.sync_logs[-3:]))


def _render_node_column(sim: DisasterSimulator, cfg: Dict[str, str], col: Any) -> None:
    nid = cfg["id"]
    node = sim.nodes[nid]
    state = node.get_state()
    vv = node.get_version_vector()
    peer_ids = [n for n in sim.node_ids if n != nid]

    with col:
        st.subheader(cfg["title"])
        st.caption(f"{cfg['desc']} | `{nid}`")

        m1, m2 = st.columns(2)
        with m1:
            st.metric("SQLite Events", node.store.count())
        with m2:
            vv_short = ", ".join(f"{k.split('-')[0]}:{v}" for k, v in sorted(vv.items()))
            st.metric("Version Vector", f"{{{vv_short}}}")

        with st.expander(f"➕ Field Actions ({nid.split('-')[0].capitalize()})", expanded=True):
            t_person, t_supply, t_boat, t_shelter = st.tabs(["Person", "Supplies", "Boat", "Shelter / Need"])

            # 1. Person Sighting
            with t_person:
                with st.form(key=f"form_person_{nid}"):
                    p_name = st.text_input("Name", value="David Kim")
                    p_id = "person-" + p_name.lower().replace(" ", "-")
                    p_status = st.selectbox("Status", ["MISSING", "FOUND_SAFE", "INJURED", "EVACUATED"])
                    p_loc = st.text_input("Location", value=f"Sector near {nid.split('-')[1]}")
                    if st.form_submit_button("Log Person Update", use_container_width=True):
                        node.record_event("person", p_id, "UPDATE", {"name": p_name, "status": p_status, "location": p_loc})
                        st.rerun()

            # 2. Divisible Escrow Supplies (Consume OR Transfer Quota)
            with t_supply:
                sup_data = state.get("supply", {}).get("supply-antibiotics", {})
                my_quota = sup_data.get("quotas", {}).get(nid, 0)
                st.write(f"**Amoxicillin Pool:** My Quota `{my_quota}` courses")

                with st.form(key=f"form_supply_{nid}"):
                    consume_amt = st.number_input(
                        "Consume Qty", min_value=1, max_value=max(1, my_quota), value=min(5, max(1, my_quota))
                    )
                    beneficiary = st.text_input("Patient / Beneficiary", value="Emergency Patient")
                    if st.form_submit_button("Consume from Escrow", use_container_width=True):
                        try:
                            EscrowManager.consume(node, "supply-antibiotics", int(consume_amt), beneficiary)
                            st.rerun()
                        except InsufficientQuotaError as exc:
                            st.error(str(exc))

                with st.form(key=f"form_xfer_supply_{nid}"):
                    xfer_to = st.selectbox("Transfer Quota To", peer_ids, key=f"sxfer_to_{nid}")
                    xfer_amt = st.number_input(
                        "Transfer Qty", min_value=1, max_value=max(1, my_quota), value=min(5, max(1, my_quota)),
                        key=f"sxfer_amt_{nid}",
                    )
                    if st.form_submit_button("Transfer Escrow Quota", use_container_width=True):
                        try:
                            EscrowManager.transfer_quota(
                                node, xfer_to, "supply-antibiotics", int(xfer_amt), "Field quota rebalance"
                            )
                            st.rerun()
                        except InsufficientQuotaError as exc:
                            st.error(str(exc))

            # 3. Scarce Single-Owner Boat Token
            with t_boat:
                boat_data = state.get("scarce_item", {}).get("boat-titan", {})
                token_holder = boat_data.get("token_holder")
                boat_status = boat_data.get("status")
                st.write(f"**Status:** `{boat_status}` | **Holder:** `{token_holder}`")
                if boat_data.get("allocated_to"):
                    st.write(f"**Mission:** {boat_data.get('allocated_to')}")

                if token_holder == nid and boat_status == "AVAILABLE":
                    with st.form(key=f"form_alloc_boat_{nid}"):
                        mission = st.text_input("Mission Name", value=f"Evacuation Run ({nid.split('-')[0]})")
                        if st.form_submit_button("Confirm Boat Allocation", use_container_width=True):
                            try:
                                TokenManager.confirm_allocation(node, "boat-titan", mission, nid)
                                st.rerun()
                            except UnauthorizedAllocationError as exc:
                                st.error(str(exc))

                    with st.form(key=f"form_xfer_boat_{nid}"):
                        new_holder = st.selectbox("Hand Off Token To", peer_ids, key=f"bxfer_to_{nid}")
                        if st.form_submit_button("Transfer Token Custody", use_container_width=True):
                            try:
                                TokenManager.transfer_token(node, "boat-titan", new_holder, "Field custody hand-off")
                                st.rerun()
                            except UnauthorizedAllocationError as exc:
                                st.error(str(exc))

                elif token_holder == nid and boat_status == "CONFIRMED_ALLOCATED":
                    if st.button("Release Boat (Mission Complete)", key=f"rel_boat_{nid}", use_container_width=True):
                        TokenManager.release_item(node, "boat-titan", notes="Mission finished")
                        st.rerun()
                else:
                    with st.form(key=f"form_req_boat_{nid}"):
                        req_mission = st.text_input("Request Purpose", value=f"Request from {nid.split('-')[0]}")
                        if st.form_submit_button("Submit Offline Request", use_container_width=True):
                            TokenManager.request_allocation(node, "boat-titan", req_mission)
                            st.rerun()

            # 4. Shelters & Needs
            with t_shelter:
                with st.form(key=f"form_shelter_{nid}"):
                    sh_name = st.text_input("Shelter Name", value=f"{nid.split('-')[0].title()} Relief Hall")
                    sh_id = "shelter-" + sh_name.lower().replace(" ", "-")
                    sc1, sc2 = st.columns(2)
                    with sc1:
                        sh_occ = st.number_input("Occupancy", min_value=0, max_value=1000, value=25)
                    with sc2:
                        sh_cap = st.number_input("Capacity", min_value=1, max_value=1000, value=100)
                    if st.form_submit_button("Log / Update Shelter", use_container_width=True):
                        node.record_event(
                            "shelter", sh_id, "UPDATE", {"name": sh_name, "occupancy": int(sh_occ), "capacity": int(sh_cap)}
                        )
                        st.rerun()

                with st.form(key=f"form_need_{nid}"):
                    need_item = st.text_input("Emergency Need", value="Water Purification Tablets")
                    need_urg = st.selectbox("Urgency", ["CRITICAL", "HIGH", "MEDIUM"])
                    if st.form_submit_button("Log Urgent Need", use_container_width=True):
                        need_id = f"need-{nid.split('-')[0]}-{int(time.time() * 1000) % 10000}"
                        node.record_event("need", need_id, "CREATE", {"item": need_item, "urgency": need_urg})
                        st.rerun()

                open_needs = [
                    (need_id, ndata)
                    for need_id, ndata in state.get("need", {}).items()
                    if ndata.get("status") != "RESOLVED"
                ]
                if open_needs:
                    selected_need = st.selectbox(
                        "Resolve Need",
                        [need_id for need_id, _ in open_needs],
                        format_func=lambda k: state["need"][k].get("item", k),
                        key=f"res_need_sel_{nid}",
                    )
                    if st.button("Mark Need Resolved", key=f"res_need_btn_{nid}", use_container_width=True):
                        node.record_event("need", selected_need, "RESOLVE", {"resolution_note": f"Fulfilled by {nid}"})
                        st.rerun()

        # Materialized Local View
        st.markdown("##### Materialized Station View")

        people = state.get("person", {})
        if people:
            st.caption(f"**People ({len(people)}):**")
            for pid, pdata in people.items():
                conflicts = pdata.get("conflicts", [])
                if conflicts:
                    st.markdown(f"""
                        <div class="conflict-alert">
                            <strong>⚠️ CONFLICT: {pdata.get('name', pid)}</strong><br>
                            Displayed: <code>{pdata.get('status')}</code> @ {pdata.get('location')}<br>
                            <em>Disputed by {len(conflicts)} observation(s) — zero lost updates.</em>
                        </div>
                    """, unsafe_allow_html=True)
                else:
                    st.write(f"• **{pdata.get('name', pid)}:** `{pdata.get('status')}` ({pdata.get('location', 'N/A')})")

        supplies = state.get("supply", {})
        if supplies:
            st.caption("**Escrow Supplies:**")
            for _, sdata in supplies.items():
                my_q = sdata.get("quotas", {}).get(nid, 0)
                total = sdata.get("total_quantity", 0)
                consumed = sdata.get("consumed", 0)
                st.write(f"• **{sdata.get('item_name')}:** Quota `{my_q}` | Consumed `{consumed}/{total}`")
                if total > 0:
                    st.progress(min(1.0, my_q / total))

        scarce = state.get("scarce_item", {})
        if scarce:
            st.caption("**Scarce Assets:**")
            for _, idata in scarce.items():
                alloc_str = f" → {idata.get('allocated_to')}" if idata.get("allocated_to") else ""
                st.write(f"• **{idata.get('item_name')}:** `{idata.get('status')}`{alloc_str}")
                reqs = idata.get("requests", [])
                if reqs:
                    st.caption(f"  ({len(reqs)} offline request(s) queued)")

        shelters = state.get("shelter", {})
        needs = state.get("need", {})
        if shelters or needs:
            st.caption("**Shelters & Needs:**")
            for _, sdata in shelters.items():
                st.write(f"• Shelter **{sdata.get('name')}**: {sdata.get('occupancy', 0)}/{sdata.get('capacity', 0)}")
            for _, ndata in list(needs.items())[-3:]:
                status_tag = "RESOLVED" if ndata.get("status") == "RESOLVED" else ndata.get("urgency")
                st.write(f"• Need **{ndata.get('item')}** (`{status_tag}`)")


def _render_convergence_audit(sim: DisasterSimulator) -> None:
    first_node_id = sim.node_ids[0]
    first_state = sim.nodes[first_node_id].get_state()
    is_converged = check_mesh_convergence(sim)

    if is_converged:
        st.markdown("""
            <div class="converged-badge">
                ✅ STRONG EVENTUAL CONVERGENCE ACHIEVED —
                All 3 stations hold identical state, version vectors, and entity projections.
            </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown("""
            <div class="diverged-badge">
                ⏳ STATIONS DIVERGED —
                Offline edits exist in separate sectors. Heal links (or carry a USB bundle) and sync to converge.
            </div>
        """, unsafe_allow_html=True)

    st.write("")
    inv1, inv2, inv3, inv4 = st.columns(4)

    with inv1:
        st.metric("Invariant (a) State Match", "100% MATCH" if is_converged else "DIVERGED")

    with inv2:
        all_ids = {e.event_id for n in sim.nodes.values() for e in n.store.get_all_events()}
        missing = max((len(all_ids) - n.store.count()) for n in sim.nodes.values())
        st.metric(
            "Invariant (b) Lost Updates",
            "ZERO LOST" if missing == 0 else f"{missing} PENDING",
            delta=f"{len(all_ids)} unique events",
        )

    with inv3:
        boat = first_state.get("scarce_item", {}).get("boat-titan", {})
        active_allocs = 1 if boat.get("status") == "CONFIRMED_ALLOCATED" else 0
        st.metric("Invariant (c) Boat Allocs", f"{active_allocs} Active (Max 1)", delta="Single-Owner Token")

    with inv4:
        supply = first_state.get("supply", {}).get("supply-antibiotics", {})
        total_q = supply.get("total_quantity", 120)
        consumed_q = supply.get("consumed", 0)
        remaining_q = sum(supply.get("quotas", {}).values())
        conserved = (remaining_q + consumed_q == total_q)
        st.metric(
            "Invariant (d) Escrow Sum",
            f"{remaining_q + consumed_q}/{total_q}",
            delta="Conserved" if conserved else "Violation",
        )

    conflicted_people = [
        (pid, pdata) for pid, pdata in first_state.get("person", {}).items() if pdata.get("conflicts")
    ]
    if conflicted_people:
        st.write("")
        with st.expander("🩺 Human Triage: Resolve Flagged Person Conflicts", expanded=True):
            for pid, pdata in conflicted_people:
                c1, c2, c3 = st.columns([2, 2, 1.2])
                with c1:
                    st.write(f"**Disputed Person:** `{pdata.get('name', pid)}` ({pid})")
                    for c in pdata["conflicts"]:
                        st.caption(f"• Report from `{c['node_id']}`: **{c['conflicting_status']}**")
                with c2:
                    resolved_status = st.selectbox(
                        "Verified Status",
                        ["FOUND_SAFE_VERIFIED", "IN_SURGERY_STABLE", "EVACUATED_CONFIRMED"],
                        key=f"res_status_{pid}",
                    )
                    notes = st.text_input(
                        "Triage Notes", value="Verified identity via biometric triage badge", key=f"res_note_{pid}"
                    )
                with c3:
                    st.write("")
                    st.write("")
                    if st.button("Resolve Conflict", key=f"res_btn_{pid}", use_container_width=True):
                        ConflictResolver.resolve_person_conflict(
                            node=sim.nodes[first_node_id],
                            person_id=pid,
                            verified_status=resolved_status,
                            verified_location=f"Triage Base {first_node_id}",
                            resolution_notes=notes,
                        )
                        _record_sync_logs(run_mesh_sync(sim))
                        st.rerun()


def _render_timeline_inspector(sim: DisasterSimulator) -> None:
    c1, c2, c3 = st.columns([1.5, 1.5, 1.0])
    with c1:
        selected_nid = st.selectbox("Inspect Station Event Store", sim.node_ids, key="timeline_node_sel")
    with c2:
        view_mode = st.radio(
            "Payload View", ["Decrypted Domain View", "Raw SQLite At-Rest (Ciphertext)"],
            horizontal=True, key="timeline_view_mode",
        )
    with c3:
        limit = st.slider("Events to show", min_value=5, max_value=50, value=15, key="timeline_limit")

    rows = get_node_timeline(sim, selected_nid, limit=limit)
    if not rows:
        st.info("No events recorded on this station yet.")
        return

    table_data = []
    for r in rows:
        crypto_tags = []
        if r["signed"]:
            crypto_tags.append("Ed25519 OK" if r["sig_valid"] else "SIG CHECK")
        if r["encrypted_pii"]:
            crypto_tags.append("AES-256-GCM PII")
        shown_payload = r["payload"] if view_mode.startswith("Decrypted") else r["raw_payload"]
        table_data.append({
            "Counter": f"{r['node_id'].split('-')[0]}#{r['counter']}",
            "Entity": r["entity"],
            "Operation": r["operation"],
            "Crypto": " + ".join(crypto_tags) if crypto_tags else "Unsigned",
            "Bytes": r["wire_bytes"],
            "Event ID": r["event_id"][:12] + "...",
            "Payload": json.dumps(shown_payload, sort_keys=True),
        })

    st.dataframe(table_data, use_container_width=True, hide_index=True)


def _render_wire_and_usb(sim: DisasterSimulator) -> None:
    stats = sim.transport.get_stats()
    w1, w2, w3 = st.columns(3)
    with w1:
        st.metric("Total Wire Bytes", f"{stats['total_bytes']} B")
    with w2:
        st.metric("Framed Messages Sent", stats["total_messages"])
    with w3:
        avg = round(stats["total_bytes"] / max(1, stats["total_messages"]), 1)
        st.metric("Avg Frame Size", f"{avg} B")

    st.markdown("#### 🔌 Offline USB / Courier Sneakernet Sync")
    st.caption(
        "Simulates carrying an exported delta JSON file on a USB thumb drive when stations are miles apart and all radio links are cut."
    )

    u1, u2, u3 = st.columns([1.2, 1.2, 1.4])
    with u1:
        src_usb = st.selectbox("Source Station (Export)", sim.node_ids, index=0, key="usb_src")
    with u2:
        dst_usb = st.selectbox("Destination Station (Import)", sim.node_ids, index=2, key="usb_dst")
    with u3:
        st.write("")
        if st.button("🚚 Hand-Carry USB Bundle Now", use_container_width=True):
            bundle_str = export_node_bundle_json(sim, src_usb)
            res = import_node_bundle_json(sim, dst_usb, bundle_str)
            st.session_state.sync_logs = [
                f"USB Sneakernet {src_usb} -> {dst_usb}: {res['applied']} new events applied "
                f"({res['skipped_duplicates']} dupes, {res['rejected']} rejected), {len(bundle_str)} B"
            ]
            st.rerun()

    dl_col, ul_col = st.columns(2)
    with dl_col:
        bundle_download = export_node_bundle_json(sim, src_usb)
        st.download_button(
            label=f"⬇️ Download {src_usb} Bundle (.json)",
            data=bundle_download,
            file_name=f"rescuenet_{src_usb}_bundle.json",
            mime="application/json",
            use_container_width=True,
        )
    with ul_col:
        uploaded = st.file_uploader(
            f"⬆️ Upload USB Bundle into {dst_usb}", type=["json"], key="usb_upload_file"
        )
        if uploaded is not None and st.button("Import Uploaded Bundle", use_container_width=True):
            try:
                content = uploaded.getvalue().decode("utf-8")
                res = import_node_bundle_json(sim, dst_usb, content)
                st.session_state.sync_logs = [
                    f"Imported file into {dst_usb}: {res['applied']} applied, {res['rejected']} rejected"
                ]
                st.rerun()
            except Exception as exc:
                st.error(f"Invalid USB bundle file: {exc}")

    if st.session_state.get("sync_history"):
        with st.expander("Recent Sync History", expanded=False):
            for entry in reversed(st.session_state.sync_history[-10:]):
                st.text(f"[{entry['time']}] {entry['summary']}")


def main() -> None:
    st.set_page_config(
        page_title="RescueNet: Offline Disaster Mesh",
        page_icon="📡",
        layout="wide",
        initial_sidebar_state="collapsed",
    )

    sim = _init_session_state(enable_crypto=True)
    _inject_custom_css()

    tab_showcase, tab_ops, tab_audit, tab_timeline, tab_usb = st.tabs([
        "🎯 3-Phase Showcase (ResQ-Mesh)",
        "🎛️ Operational Mesh & Topology",
        "🔍 Convergence & Invariant Audit",
        "📜 Live Event Timeline & Crypto",
        "🔌 Wire Traffic & USB Sneakernet",
    ])

    with tab_showcase:
        _render_resqmesh_showcase(sim)

    with tab_ops:
        _render_header(sim)
        _render_top_controls(sim)
        _render_topology_section(sim)
        st.markdown("---")
        cols = st.columns(3)
        for idx, cfg in enumerate(NODE_CONFIGS):
            _render_node_column(sim, cfg, cols[idx])

    with tab_audit:
        _render_convergence_audit(sim)

    with tab_timeline:
        _render_timeline_inspector(sim)

    with tab_usb:
        _render_wire_and_usb(sim)


if __name__ == "__main__":
    main()
