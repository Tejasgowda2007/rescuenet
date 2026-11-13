"""
RescueNet: Decentralized Offline-First Disaster Coordination Command Center.
National-Level Hackathon Mentor Evaluation Dashboard.
Tagline: "When the network dies, coordination shouldn't."
"""

from __future__ import annotations
import os
import sys
import time
from typing import Any, Dict, List

# Ensure project root is on sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import streamlit as st
from simulator.engine import DisasterSimulator
from ui.styles import get_css
from ui.controller import (
    create_ui_simulator,
    run_scenario_preset,
)
from ui.components import (
    render_command_center_header,
    render_controls_bar,
    render_mesh_network_monitor,
    render_incident_overview,
    render_rescue_operations,
    render_partition_demo_stepper,
    render_sync_monitor,
    render_security_centre,
    render_resource_allocation_safety,
    render_event_audit_feed,
    render_long_range_comms,
    render_system_health_scorecard,
)
from auth.database import (
    init_admin_account,
    get_user_by_username,
    check_rate_limit,
    record_login_attempt,
    log_audit,
)
from auth.crypto import verify_password


def _init_session_state(enable_crypto: bool = True) -> DisasterSimulator:
    """Initialize or retrieve active DisasterSimulator and session state."""
    if "theme" not in st.session_state:
        st.session_state.theme = "dark"
    if "sim" not in st.session_state:
        st.session_state.crypto_enabled = enable_crypto
        st.session_state.sim = create_ui_simulator(enable_crypto=enable_crypto)
        st.session_state.sync_logs = ["RescueNet Command Center Initialized: All 3 stations online & synchronized."]
        st.session_state.step = 1
        st.session_state.resolved = False
    return st.session_state.sim


def _reset_demo(enable_crypto: bool | None = None) -> None:
    """Tear down existing simulator and bootstrap a clean mesh baseline in < 2 seconds."""
    if enable_crypto is None:
        enable_crypto = st.session_state.get("crypto_enabled", True)
    if "sim" in st.session_state:
        st.session_state.sim.close()
    st.session_state.crypto_enabled = enable_crypto
    st.session_state.sim = create_ui_simulator(enable_crypto=enable_crypto)
    st.session_state.sync_logs = ["System reset to clean, fully-converged baseline."]
    st.session_state.step = 1
    st.session_state.resolved = False


def main() -> None:
    st.set_page_config(
        page_title="RescueNet Command Center",
        page_icon="📡",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    init_admin_account()

    # Authentication Gate
    if "auth_user" not in st.session_state:
        st.markdown(get_css(st.session_state.get("theme", "dark")), unsafe_allow_html=True)
        _, col2, _ = st.columns([1, 2, 1])
        with col2:
            st.markdown("""
                <div style="text-align: center; margin-top: 50px; margin-bottom: 25px;">
                    <div style="display: inline-block; padding: 12px; background: #0B121D; border: 1px solid #00E5FF; border-radius: 12px; margin-bottom: 15px;">
                        <span style="font-size: 2rem;">📡</span>
                    </div>
                    <h1 style="color: #00E5FF; font-weight: 900; letter-spacing: 2px; margin-bottom: 4px;">
                        RESCUENET <span style="color: #FFFFFF;">COMMAND CENTER</span>
                    </h1>
                    <p style="color: #94A3B8; font-size: 0.85rem; text-transform: uppercase; letter-spacing: 1.5px; font-weight: 600;">
                        Offline-First Disaster Coordination System
                    </p>
                    <p style="color: #FF6B00; font-size: 0.85rem; font-style: italic;">
                        "When the network dies, coordination shouldn't."
                    </p>
                </div>
            """, unsafe_allow_html=True)

            with st.form("login_form", clear_on_submit=False):
                username = st.text_input("Operator Callsign / Username", placeholder="e.g. admin")
                password = st.text_input("Security Passcode", type="password", placeholder="Enter operator password")
                submitted = st.form_submit_button("AUTHENTICATE & ENTER", use_container_width=True)

                if submitted:
                    uname = username.strip()
                    is_limited, remaining = check_rate_limit(uname)
                    if is_limited:
                        st.error(f"Too many failed login attempts. Security lockout active. Wait {remaining}s.")
                    else:
                        user = get_user_by_username(uname)
                        if user and verify_password(password, user["password_hash"]):
                            if user.get("is_active"):
                                record_login_attempt(uname, True)
                                log_audit("STREAMLIT_LOGIN_SUCCESS", user_id=user["id"], username=user["username"])
                                st.session_state.auth_user = user
                                st.rerun()
                            else:
                                st.error("Account is disabled. Contact system administrator.")
                        else:
                            record_login_attempt(uname, False)
                            log_audit("STREAMLIT_LOGIN_FAILED", username=uname)
                            st.error("Invalid operator username or password.")

            st.markdown("""
                <div style="text-align: center; margin-top: 20px; font-size: 0.75rem; color: #64748B;">
                    Defense-Grade Argon2id Hashing &bull; Brute-Force Rate Limiting Active
                </div>
            """, unsafe_allow_html=True)
        return

    sim = _init_session_state(enable_crypto=True)

    # Sidebar: System Controls & Presets
    with st.sidebar:
        user = st.session_state.auth_user
        st.markdown(f"### 👤 Operator Callsign")
        st.markdown(f"**User:** `{user['username']}`")
        st.markdown(f"**Role:** `{user['role']}`")
        if st.button("🔒 Logout", key="sb_logout_btn", use_container_width=True):
            log_audit("STREAMLIT_LOGOUT", user_id=user["id"], username=user["username"])
            del st.session_state["auth_user"]
            st.rerun()

        st.markdown("---")
        st.markdown("### ⚙️ Command Settings")
        theme_choice = st.radio(
            "Visual Palette",
            ["Dark Operations Center (Recommended)", "Light Mission Control"],
            index=0 if st.session_state.get("theme", "dark") == "dark" else 1,
            key="theme_sel",
        )
        st.session_state.theme = "dark" if "Dark" in theme_choice else "light"

        st.markdown("---")
        st.markdown("### 🧭 Quick Scenario Presets")
        if st.button("🌊 Flash Flood Preset", key="sb_preset_flood", use_container_width=True):
            st.session_state.sync_logs = run_scenario_preset(sim, "flash_flood")
            st.toast("Flash Flood scenario applied.", icon="🌊")
            st.rerun()

        if st.button("💊 Supply Rebalance", key="sb_preset_supply", use_container_width=True):
            st.session_state.sync_logs = run_scenario_preset(sim, "supply_crunch")
            st.toast("Supply rebalance scenario applied.", icon="💊")
            st.rerun()

        if st.button("🔁 2-Hop Relay Mule", key="sb_preset_mule", use_container_width=True):
            st.session_state.sync_logs = run_scenario_preset(sim, "chain_mule")
            st.toast("2-Hop relay scenario applied.", icon="🔁")
            st.rerun()

        st.markdown("---")
        st.markdown("### 🎯 Judge / Mentor Quick Jump")
        st.caption("Jump directly to key demonstration modules:")
        st.markdown("""
            - **Live Mesh:** Topology & Link Switches
            - **5-Step Demo:** Offline Partition & Convergence
            - **Escrow Invariant:** Resource Allocation Safety
            - **Crypto Center:** Ed25519 & AES-256-GCM
        """)
        st.markdown("---")
        st.caption("RescueNet v2.5 • Offline-First Disaster Response System")

    # Inject Custom CSS Theme
    st.markdown(get_css(st.session_state.get("theme", "dark")), unsafe_allow_html=True)

    # 1. COMMAND CENTRE HEADER
    render_command_center_header(sim)

    # Quick Action Bar
    render_controls_bar(sim, _reset_demo)
    st.write("")

    # 2-11. MAIN OPERATIONAL SECTIONS VIA TAB NAVIGATION
    (
        tab_incidents,
        tab_mesh,
        tab_demo,
        tab_operations,
        tab_sync,
        tab_security,
        tab_allocation,
        tab_audit,
        tab_long_range,
        tab_health,
    ) = st.tabs([
        "🚨 Incident Command",
        "📡 Live Mesh & Stations",
        "🎯 5-Step Partition Demo",
        "🩺 Rescue Operations",
        "🔄 Sync & Delta Monitor",
        "🔐 Security & Cryptography",
        "⚖️ Resource Allocation Safety",
        "📜 Event Store & Audit",
        "📻 Long-Range Comms",
        "🩺 System Diagnostics",
    ])

    with tab_incidents:
        render_incident_overview(sim)

    with tab_mesh:
        render_mesh_network_monitor(sim)

    with tab_demo:
        render_partition_demo_stepper(sim)

    with tab_operations:
        render_rescue_operations(sim)

    with tab_sync:
        render_sync_monitor(sim)

    with tab_security:
        render_security_centre(sim)

    with tab_allocation:
        render_resource_allocation_safety(sim)

    with tab_audit:
        render_event_audit_feed(sim)

    with tab_long_range:
        render_long_range_comms()

    with tab_health:
        render_system_health_scorecard(sim)


if __name__ == "__main__":
    main()
