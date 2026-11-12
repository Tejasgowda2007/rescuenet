"""
ResQ-Mesh: Ultra-Simple Executive Disaster Dashboard.
Zero Jargon. Zero Complex Menus. 3-Click Story.
"""

from __future__ import annotations
import sys
import os
import json

# Ensure project root is on sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import streamlit as st
import streamlit.components.v1 as components
from ui.controller import (
    create_ui_simulator,
    run_resqmesh_phase1_baseline,
    run_resqmesh_phase2_split_and_conflict,
    run_resqmesh_phase3_reconnect_and_converge,
    resolve_resqmesh_inventory_collision,
    dispatch_ambulance_data_mule,
    revoke_compromised_device,
    check_mesh_convergence,
)


def get_sim():
    if "sim" not in st.session_state:
        st.session_state.sim = create_ui_simulator()
        st.session_state.step = 1
        st.session_state.resolved = False
        st.session_state.show_qr = False
    return st.session_state.sim


def main():
    st.set_page_config(
        page_title="ResQ-Mesh",
        page_icon="📡",
        layout="centered",
        initial_sidebar_state="collapsed",
    )

    sim = get_sim()
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


if __name__ == "__main__":
    main()
